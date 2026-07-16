#!/usr/bin/env perl
use strict;
use warnings;
use Getopt::Long qw(GetOptions);
use File::Path qw(make_path);
use File::Spec;
use FindBin qw($RealBin);

my ($fsdb, $begin, $end, $out_dir);
my @signals;
my @times;
my $max_rows = 200;
my $help = 0;
my $kdebug_override;

GetOptions(
    'fsdb=s'     => \$fsdb,
    'signal=s@'  => \@signals,
    'begin=s'    => \$begin,
    'start=s'    => \$begin,
    'end=s'      => \$end,
    'stop=s'     => \$end,
    'time=s@'    => \@times,
    'max-rows=i' => \$max_rows,
    'kdebug-bin=s' => \$kdebug_override,
    'out=s'      => \$out_dir,
    'help|h'     => \$help,
) or usage(2);
usage(0) if $help;
usage(2) unless defined $fsdb && defined $begin && defined $end
    && defined $out_dir && @signals;

sub usage {
    my ($rc) = @_;
    print STDERR <<'USAGE';
Usage: waveform_window.pl --fsdb FILE --signal NAME [--signal NAME ...]
                          --begin TIME --end TIME [--time TIME ...]
                          [--max-rows N] [--kdebug-bin CMD] --out DIR

Environment:
  KDEBUG_BIN, KVERIF_HOME

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
    my ($value) = @_;
    my $resolved = find_executable($value);
    defined $resolved or die "kdebug is not executable: $value\n";
    return $resolved;
}

my $repo_tool = File::Spec->rel2abs(
    File::Spec->catfile($RealBin, '..', '..', '..', 'tools', 'kdebug')
);
my $kdebug;
if (defined $kdebug_override && length $kdebug_override) {
    $kdebug = configured_command($kdebug_override);
} elsif (defined $ENV{KDEBUG_BIN} && length $ENV{KDEBUG_BIN}) {
    $kdebug = configured_command($ENV{KDEBUG_BIN});
} elsif (defined $ENV{KVERIF_HOME}
         && -x File::Spec->catfile($ENV{KVERIF_HOME}, 'tools', 'kdebug')) {
    $kdebug = File::Spec->catfile($ENV{KVERIF_HOME}, 'tools', 'kdebug');
} elsif (-x $repo_tool) {
    $kdebug = $repo_tool;
} else {
    $kdebug = find_executable('kdebug');
}
defined $kdebug or die "cannot find kdebug; use --kdebug-bin, KDEBUG_BIN, KVERIF_HOME, or PATH\n";
make_path($out_dir);

my $session = 'perl_wave_' . ($ENV{USER} || 'user') . '_' . $$;
my $opened = 0;

sub run_json {
    my ($output, @command) = @_;
    open my $pipe, '-|', @command or die "cannot start @command: $!\n";
    local $/;
    my $text = <$pipe>;
    $text = '' unless defined $text;
    close $pipe;
    my $rc = $? >> 8;

    open my $fh, '>:encoding(UTF-8)', $output or die "cannot write $output: $!\n";
    print {$fh} $text;
    close $fh;

    die "command failed rc=$rc; saved to $output\n" if $rc != 0;
    return;
}

sub safe_name {
    my ($value) = @_;
    $value =~ s/[^A-Za-z0-9_.-]/_/g;
    return $value;
}

sub close_session {
    return unless $opened;
    eval {
        run_json(
            File::Spec->catfile($out_dir, 'session.close.json'),
            $kdebug, '--json', 'session-close', '--session', $session
        );
    };
    warn $@ if $@;
    $opened = 0;
}

$SIG{INT} = sub { close_session(); exit 130; };
$SIG{TERM} = sub { close_session(); exit 143; };
END { close_session(); }

run_json(
    File::Spec->catfile($out_dir, 'session.open.json'),
    $kdebug, '--json', 'session-open', '--name', $session, '--fsdb', $fsdb
);
$opened = 1;

for my $signal (@signals) {
    run_json(
        File::Spec->catfile($out_dir, 'scan.' . safe_name($signal) . '.json'),
        $kdebug, '--json', 'action', 'signal.scan',
        '--session', $session,
        '--arg', "signal=$signal",
        '--arg', "begin=$begin",
        '--arg', "end=$end",
        '--arg', 'format=hex',
        '--max-rows', $max_rows,
    );
}

for my $time (@times) {
    my @command = ($kdebug, '--json', 'value-batch', '--session', $session);
    push @command, map { ('--signal', $_) } @signals;
    push @command, '--time', $time, '--format', 'hex';
    run_json(
        File::Spec->catfile($out_dir, 'sample.' . safe_name($time) . '.json'),
        @command,
    );
}

close_session();
print "waveform results: $out_dir\n";
