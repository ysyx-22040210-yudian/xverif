#!/usr/bin/env perl
use strict;
use warnings;
use Getopt::Long qw(GetOptions);
use File::Path qw(make_path);
use File::Spec;
use FindBin qw($RealBin);

my ($fsdb, $signal, $begin, $end, $out_dir);
my $max_rows = 200;
my $min_changes = 1;
my $max_unknown = 0;
my $require_complete = 0;
my $help = 0;
my ($kdebug_override, $json_python_override, $json_helper_override);

GetOptions(
    'fsdb=s'            => \$fsdb,
    'signal=s'          => \$signal,
    'begin|start=s'     => \$begin,
    'end|stop=s'        => \$end,
    'max-rows=i'        => \$max_rows,
    'min-changes=i'     => \$min_changes,
    'max-unknown=i'     => \$max_unknown,
    'require-complete!' => \$require_complete,
    'kdebug-bin=s'      => \$kdebug_override,
    'json-python=s'     => \$json_python_override,
    'json-helper=s'     => \$json_helper_override,
    'out=s'             => \$out_dir,
    'help|h'            => \$help,
) or usage(2);
usage(0) if $help;
usage(2) unless defined $fsdb && defined $signal && defined $begin
    && defined $end && defined $out_dir;
usage(2) if $max_rows < 0 || $min_changes < 0 || $max_unknown < 0;

sub usage {
    my ($rc) = @_;
    print STDERR <<'USAGE';
Usage: signal_health.pl --fsdb FILE --signal NAME --begin TIME --end TIME
                        [--max-rows N] [--min-changes N]
                        [--max-unknown N] [--require-complete]
                        [--kdebug-bin CMD] [--json-python CMD]
                        [--json-helper FILE] --out DIR

The script invokes kdebug, parses signal.scan JSON, and emits conclusion.json.
Resolution: explicit option, environment, KVERIF_HOME/tools, repository, PATH.
USAGE
    exit $rc;
}

sub find_executable {
    my ($command) = @_;
    return unless defined $command && length $command;
    return File::Spec->rel2abs($command) if -f $command && -x $command;
    for my $directory (File::Spec->path()) {
        my $candidate = File::Spec->catfile($directory, $command);
        return File::Spec->rel2abs($candidate) if -f $candidate && -x $candidate;
    }
    return;
}

sub configured_command {
    my ($value, $label) = @_;
    my $resolved = find_executable($value);
    defined $resolved or die "$label is not executable: $value\n";
    return $resolved;
}

my $repo_tool = File::Spec->rel2abs(
    File::Spec->catfile($RealBin, '..', '..', '..', 'tools', 'kdebug')
);
my $kdebug;
if (defined $kdebug_override && length $kdebug_override) {
    $kdebug = configured_command($kdebug_override, 'kdebug');
} elsif (defined $ENV{KDEBUG_BIN} && length $ENV{KDEBUG_BIN}) {
    $kdebug = configured_command($ENV{KDEBUG_BIN}, 'kdebug');
} elsif (defined $ENV{KVERIF_HOME}
         && -x File::Spec->catfile($ENV{KVERIF_HOME}, 'tools', 'kdebug')) {
    $kdebug = File::Spec->catfile($ENV{KVERIF_HOME}, 'tools', 'kdebug');
} elsif (-x $repo_tool) {
    $kdebug = $repo_tool;
} else {
    $kdebug = find_executable('kdebug');
}
defined $kdebug or die "cannot find kdebug; use --kdebug-bin, KDEBUG_BIN, KVERIF_HOME, or PATH\n";

my $python_setting = defined $json_python_override && length $json_python_override
    ? $json_python_override
    : defined $ENV{KVERIF_JSON_PYTHON} && length $ENV{KVERIF_JSON_PYTHON}
        ? $ENV{KVERIF_JSON_PYTHON}
        : defined $ENV{PYTHON} && length $ENV{PYTHON}
            ? $ENV{PYTHON}
            : undef;
my $json_python;
if (defined $python_setting) {
    $json_python = configured_command($python_setting, 'JSON Python');
} else {
    $json_python = find_executable('python3') || find_executable('python');
}
defined $json_python or die "cannot find Python 3; use --json-python, KVERIF_JSON_PYTHON, or PYTHON\n";
system($json_python, '-c', 'import json, sys; raise SystemExit(0 if sys.version_info[0] >= 3 else 1)') == 0
    or die "JSON helper requires Python 3: $json_python\n";

my $local_helper = File::Spec->rel2abs(File::Spec->catfile($RealBin, '..', 'json_response.py'));
my $home_helper = defined $ENV{KVERIF_HOME}
    ? File::Spec->catfile($ENV{KVERIF_HOME}, 'examples', 'secondary_development', 'json_response.py')
    : '';
my $json_helper = defined $json_helper_override && length $json_helper_override
    ? $json_helper_override
    : defined $ENV{KVERIF_JSON_HELPER} && length $ENV{KVERIF_JSON_HELPER}
        ? $ENV{KVERIF_JSON_HELPER}
        : -f $local_helper
            ? $local_helper
            : length $home_helper && -f $home_helper
                ? $home_helper
                : $local_helper;
-f $json_helper or die "JSON helper is missing: $json_helper\n";
make_path($out_dir);

my $response = File::Spec->catfile($out_dir, 'tool-response.json');
my $stderr_file = File::Spec->catfile($out_dir, 'tool-response.stderr');
my $report = File::Spec->catfile($out_dir, 'conclusion.json');

sub run_redirected {
    my ($stdout_path, $stderr_path, @command) = @_;
    my $pid = fork();
    defined $pid or die "fork failed: $!\n";
    if ($pid == 0) {
        open STDOUT, '>:encoding(UTF-8)', $stdout_path
            or die "cannot write $stdout_path: $!\n";
        open STDERR, '>:encoding(UTF-8)', $stderr_path
            or die "cannot write $stderr_path: $!\n";
        exec {$command[0]} @command;
        die "cannot exec $command[0]: $!\n";
    }
    waitpid($pid, 0);
    return $? >> 8;
}

sub capture_line {
    my (@command) = @_;
    open my $pipe, '-|', @command or die "cannot start @command: $!\n";
    my $line = <$pipe>;
    close $pipe;
    my $rc = $? >> 8;
    die "command failed rc=$rc: @command\n" if $rc != 0;
    defined $line or die "command produced no output: @command\n";
    chomp $line;
    $line =~ s/\r$//;
    return $line;
}

my @tool_command = (
    $kdebug, '--json', 'action', 'signal.scan',
    '--fsdb', $fsdb,
    '--arg', "signal=$signal",
    '--arg', "begin=$begin",
    '--arg', "end=$end",
    '--arg', 'format=hex',
    '--max-rows', $max_rows,
);
my $tool_rc = run_redirected($response, $stderr_file, @tool_command);
die "kdebug failed rc=$tool_rc; see $stderr_file\n" if $tool_rc != 0;

system($json_python, $json_helper, 'check-ok', $response) == 0
    or die "tool returned ok=false; see $response\n";
my $stats = capture_line($json_python, $json_helper, 'wave-stats', $response);
my ($change_count, $unknown_count, $truncated) = split /\t/, $stats;
defined $truncated or die "invalid wave-stats output: $stats\n";

my $conclusion = 'HEALTHY';
my $reason = 'signal activity satisfies all configured gates';
if ($require_complete && $truncated eq 'true') {
    $conclusion = 'INCOMPLETE';
    $reason = 'signal.scan was truncated, so the complete window was not evaluated';
} elsif ($unknown_count > $max_unknown) {
    $conclusion = 'UNKNOWN_VALUES';
    $reason = 'unknown_count exceeds the configured maximum';
} elsif ($change_count < $min_changes) {
    $conclusion = 'INACTIVE';
    $reason = 'change_count is below the configured minimum';
}

my @report_command = (
    $json_python, $json_helper, 'signal-health-report',
    '--output', $report, '--language', 'perl', '--signal', $signal,
    '--response', $response, '--change-count', $change_count,
    '--unknown-count', $unknown_count, '--truncated', $truncated,
    '--min-changes', $min_changes, '--max-unknown', $max_unknown,
    '--require-complete', $require_complete ? 'true' : 'false',
    '--conclusion', $conclusion, '--reason', $reason,
);
system(@report_command) == 0 or die "failed to write conclusion report\n";

print "signal health: $conclusion ($reason)\n";
print "report: $report\n";
exit($conclusion eq 'HEALTHY' ? 0 : 3);
