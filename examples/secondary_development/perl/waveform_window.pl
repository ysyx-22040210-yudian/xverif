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

GetOptions(
    'fsdb=s'     => \$fsdb,
    'signal=s@'  => \@signals,
    'begin=s'    => \$begin,
    'start=s'    => \$begin,
    'end=s'      => \$end,
    'stop=s'     => \$end,
    'time=s@'    => \@times,
    'max-rows=i' => \$max_rows,
    'out=s'      => \$out_dir,
    'help|h'     => \$help,
) or usage(2);
usage(0) if $help;
usage(2) unless defined $fsdb && defined $begin && defined $end
    && defined $out_dir && @signals;

my $default_tool = File::Spec->rel2abs(
    File::Spec->catfile($RealBin, '..', '..', '..', 'tools', 'kdebug')
);
my $kdebug = $ENV{KDEBUG_BIN} || $default_tool;
-x $kdebug or die "kdebug is not executable: $kdebug\n";
make_path($out_dir);

my $session = 'perl_wave_' . ($ENV{USER} || 'user') . '_' . $$;
my $opened = 0;

sub usage {
    my ($rc) = @_;
    print STDERR <<'USAGE';
Usage: waveform_window.pl --fsdb FILE --signal NAME [--signal NAME ...]
                          --begin TIME --end TIME [--time TIME ...]
                          [--max-rows N] --out DIR

Environment:
  KDEBUG_BIN  Absolute kdebug command. Defaults to <repo>/tools/kdebug.
USAGE
    exit $rc;
}

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
