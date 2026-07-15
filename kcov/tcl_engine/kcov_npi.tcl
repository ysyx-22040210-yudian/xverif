proc json_escape {s} {
    set out ""
    set n [string length $s]
    for {set i 0} {$i < $n} {incr i} {
        set c [string index $s $i]
        scan $c %c code
        switch -- $c {
            "\"" {append out "\\\""}
            "\\" {append out "\\\\"}
            "\b" {append out "\\b"}
            "\f" {append out "\\f"}
            "\n" {append out "\\n"}
            "\r" {append out "\\r"}
            "\t" {append out "\\t"}
            default {
                if {$code < 32} {
                    append out [format "\\u%04x" $code]
                } else {
                    append out $c
                }
            }
        }
    }
    return $out
}

proc json_string {s} {
    return "\"[json_escape $s]\""
}

proc json_value {v} {
    if {$v eq "__JSON_NULL__"} {return "null"}
    if {$v eq "__JSON_TRUE__"} {return "true"}
    if {$v eq "__JSON_FALSE__"} {return "false"}
    if {[string is integer -strict $v] || [string is double -strict $v]} {return $v}
    return [json_string $v]
}

proc json_array {items} {
    set out {[}
    set first 1
    foreach item $items {
        if {!$first} {append out ","}
        set first 0
        append out [json_value $item]
    }
    append out {]}
    return $out
}

proc json_array_raw {items} {
    set out {[}
    set first 1
    foreach item $items {
        if {!$first} {append out ","}
        set first 0
        append out $item
    }
    append out {]}
    return $out
}

proc json_object {pairs} {
    set out "\{"
    set first 1
    foreach {k v} $pairs {
        if {!$first} {append out ","}
        set first 0
        append out [json_string $k] ":"
        append out [json_value $v]
    }
    append out "\}"
    return $out
}

proc json_object_raw {pairs} {
    set out "\{"
    set first 1
    foreach {k v} $pairs {
        if {!$first} {append out ","}
        set first 0
        append out [json_string $k] ":"
        append out $v
    }
    append out "\}"
    return $out
}

proc write_response_raw {json_text} {
    if {![info exists ::env(KCOV_TCL_RESPONSE_JSON)] || $::env(KCOV_TCL_RESPONSE_JSON) eq ""} {
        puts $json_text
        return
    }
    set fp [open $::env(KCOV_TCL_RESPONSE_JSON) w]
    puts $fp $json_text
    close $fp
}

proc ok_data {pairs} {
    write_response_raw [json_object_raw [list ok true data [json_object_raw $pairs]]]
}

proc fail_data {code message} {
    write_response_raw [json_object_raw [list ok false error [json_object [list code $code message $message]]]]
}

proc env_or_empty {name} {
    if {[info exists ::env($name)]} {return $::env($name)}
    return ""
}

proc env_flag {name} {
    set v [string tolower [env_or_empty $name]]
    expr {$v eq "1" || $v eq "true" || $v eq "yes" || $v eq "on"}
}

proc metric_list {} {
    set raw [env_or_empty KCOV_TCL_METRICS]
    set out {}
    foreach item [split $raw "\n"] {
        set item [string trim $item]
        if {$item ne ""} {lappend out $item}
    }
    if {[llength $out] == 0} {
        set out {line toggle branch condition fsm assert functional}
    }
    return $out
}

proc source_l1 {} {
    if {[info exists ::env(NPIL1_PATH)] && [file exists "$::env(NPIL1_PATH)/npi_L1.tcl"]} {
        source "$::env(NPIL1_PATH)/npi_L1.tcl"
        return
    }
    if {[info exists ::env(VERDI_HOME)] && [file exists "$::env(VERDI_HOME)/share/NPI/L1/TCL/npi_L1.tcl"]} {
        source "$::env(VERDI_HOME)/share/NPI/L1/TCL/npi_L1.tcl"
        return
    }
    error "cannot locate npi_L1.tcl; set VERDI_HOME or NPIL1_PATH"
}

proc cov_get_str {hdl prop} {
    if {$hdl eq ""} {return ""}
    if {[catch {npi_cov_get_str -type $prop -ref $hdl} v]} {return ""}
    return $v
}

proc cov_get {hdl prop test} {
    if {$hdl eq ""} {return ""}
    if {[catch {npi_cov_get -type $prop -ref $hdl -test $test} v]} {return ""}
    return $v
}

proc cov_handle {hdl typ} {
    if {$hdl eq ""} {return ""}
    if {[catch {npi_cov_handle -type $typ -ref $hdl} v]} {return ""}
    return $v
}

proc cov_iter_children {hdl typ} {
    set out {}
    if {[catch {npi_cov_iter_start -type $typ -ref $hdl} iter] || $iter eq ""} {
        return $out
    }
    while {![catch {npi_cov_iter_next -iter $iter} child] && $child ne ""} {
        lappend out $child
    }
    catch {npi_cov_iter_stop -iter $iter}
    return $out
}

proc cov_has_status {hdl status test} {
    if {$hdl eq ""} {return 0}
    if {[catch {npi_cov_has_status -type $status -ref $hdl -test $test} v]} {return 0}
    expr {$v ne "" && $v != 0}
}

proc parent_scope {full_name} {
    set idx [string last "." $full_name]
    if {$idx < 0} {return "__JSON_NULL__"}
    return [string range $full_name 0 [expr {$idx - 1}]]
}

proc depth_of {full_name} {
    if {$full_name eq ""} {return 0}
    expr {[llength [split $full_name "."]] - 1}
}

proc basename_of {full_name fallback} {
    if {$full_name eq ""} {return $fallback}
    set idx [string last "." $full_name]
    if {$idx < 0} {return $full_name}
    return [string range $full_name [expr {$idx + 1}] end]
}

proc evidence_json {hdl test} {
    set file [cov_get_str $hdl npiCovFileName]
    set line [cov_get $hdl npiCovLineNo $test]
    if {$line eq ""} {set line [cov_get $hdl npiCovLineNo ""]}
    return [json_object [list file $file line [expr {$line eq "" ? "__JSON_NULL__" : $line}]]]
}

proc valid_evidence {hdl test} {
    set file [cov_get_str $hdl npiCovFileName]
    set line [cov_get $hdl npiCovLineNo $test]
    if {$line eq ""} {set line [cov_get $hdl npiCovLineNo ""]}
    expr {$file ne "" && [string is integer -strict $line] && $line > 0}
}

proc source_json {typ name full_name hdl test} {
    if {![valid_evidence $hdl $test]} {return ""}
    return [json_object_raw [list \
        type [json_string $typ] \
        name [json_string $name] \
        full_name [json_string $full_name] \
        evidence [evidence_json $hdl $test]]]
}

proc status_array {hdl test covered coverable} {
    set flags {}
    if {[catch {
        if {$coverable ne "" && $coverable > 0 && $covered >= $coverable} {
            lappend flags covered
        } else {
            lappend flags not_covered
        }
    }]} {
        lappend flags not_covered
    }
    foreach {status label} {
        npiCovStatusExcluded excluded
        npiCovStatusPartiallyExcluded partially_excluded
        npiCovStatusExcludedAtCompileTime excluded_at_compile_time
        npiCovStatusExcludedAtReportTime excluded_at_report_time
        npiCovStatusUnreachable unreachable
        npiCovStatusIllegal illegal
        npiCovStatusProven proven
        npiCovStatusAttempted attempted
        npiCovStatusPartiallyAttempted partially_attempted
    } {
        if {[cov_has_status $hdl $status $test]} {lappend flags $label}
    }
    return [json_array $flags]
}

proc coverage_value {hdl test} {
    set value [cov_get $hdl npiCovValue $test]
    if {$value eq ""} {set value [cov_get $hdl npiCovValue ""]}
    if {$value eq "" || $value eq "-1"} {return "__JSON_NULL__"}
    return $value
}

proc count_value {hdl test} {
    set value [cov_get $hdl npiCovSize $test]
    if {$value eq ""} {set value [cov_get $hdl npiCovSize ""]}
    if {$value eq ""} {return "null"}
    return $value
}

proc row_base {metric typ scope name full_name hdl test row_source path_pairs} {
    set covered [cov_get $hdl npiCovCovered $test]
    set coverable [cov_get $hdl npiCovCoverable ""]
    if {$coverable eq ""} {set coverable [cov_get $hdl npiCovCoverable $test]}
    if {$covered eq ""} {set covered 0}
    if {$coverable eq ""} {return ""}
    set missing [expr {int($coverable) - int($covered)}]
    set pct "null"
    if {$coverable > 0} {set pct [expr {100.0 * double($covered) / double($coverable)}]}
    set scope_json [expr {$scope eq "__JSON_NULL__" ? "null" : [json_string $scope]}]
    set pairs [list \
        metric [json_string $metric] \
        type [json_string $typ] \
        scope $scope_json \
        name [json_string $name] \
        full_name [json_string $full_name] \
        covered $covered \
        coverable $coverable \
        missing $missing \
        count [count_value $hdl $test] \
        coverage_pct $pct \
        status [status_array $hdl $test $covered $coverable]]
    if {$row_source ne ""} {
        lappend pairs evidence [dict get $row_source evidence]
    } else {
        lappend pairs evidence [evidence_json $hdl $test]
    }
    foreach {k v} $path_pairs {
        lappend pairs $k $v
    }
    return [json_object_raw $pairs]
}

proc append_inherited_source {row source own_source} {
    if {$source eq "" || $source eq $own_source} {return $row}
    set extra [json_object_raw [list \
        inherited true \
        type [json_string [dict get $source type]] \
        name [json_string [dict get $source name]] \
        full_name [json_string [dict get $source full_name]]]]
    set row [string range $row 0 end-1]
    append row ",\"evidence_source\":" $extra "\}"
    return $row
}

proc source_dict {typ name full_name hdl test} {
    set src [source_json $typ $name $full_name $hdl $test]
    if {$src eq ""} {return ""}
    return [dict create \
        type $typ \
        name $name \
        full_name $full_name \
        evidence [evidence_json $hdl $test]]
}

proc term_summary {hdl child_type test} {
    set parts {}
    foreach term [cov_iter_children $hdl $child_type] {
        set label [cov_get_str $term npiCovName]
        if {$label eq ""} {set label [cov_get_str $term npiCovFullName]}
        set value [coverage_value $term $test]
        if {$label ne "" && $value ne "__JSON_NULL__" && $value ne $label} {
            lappend parts "$label:$value"
        } elseif {$label ne ""} {
            lappend parts $label
        } elseif {$value ne "__JSON_NULL__"} {
            lappend parts $value
        }
    }
    return [join $parts ";"]
}

proc append_code_path {metric typ hdl test name full_name path_var} {
    upvar $path_var path
    set label [expr {$full_name ne "" ? $full_name : $name}]
    if {$metric eq "toggle"} {
        if {$typ eq "npiCovSignal"} {
            dict set path toggle_signal [json_string $label]
        } elseif {$typ eq "npiCovSignalBit"} {
            dict set path toggle_bit [json_string $label]
            if {![dict exists $path toggle_signal]} {
                set idx [string last "\[" $label]
                if {$idx > 0} {dict set path toggle_signal [json_string [string range $label 0 [expr {$idx - 1}]]]}
            }
        } elseif {$typ eq "npiCovToggleBin"} {
            set trans [cov_get $hdl npiCovToggleType $test]
            if {$trans eq "" || $trans eq "-1"} {set trans $name}
            if {$trans ne ""} {dict set path toggle_transition [json_string $trans]}
        }
    } elseif {$metric eq "condition"} {
        if {$typ eq "npiCovCondition"} {
            dict set path condition [json_string $label]
            set terms [term_summary $hdl npiCovConditionTerm $test]
            if {$terms ne ""} {dict set path condition_terms [json_string $terms]}
        } elseif {$typ eq "npiCovConditionBin"} {
            set value [coverage_value $hdl $test]
            if {$value eq "__JSON_NULL__"} {set value $name}
            dict set path condition_bin [json_string $value]
        }
    } elseif {$metric eq "branch"} {
        if {$typ eq "npiCovBranch"} {
            dict set path branch [json_string $label]
            set terms [term_summary $hdl npiCovBranchTerm $test]
            if {$terms ne ""} {dict set path branch_terms [json_string $terms]}
        } elseif {$typ eq "npiCovBranchBin"} {
            set value [coverage_value $hdl $test]
            if {$value eq "__JSON_NULL__"} {set value $name}
            dict set path branch_bin [json_string $value]
        }
    }
}

proc walk_code_leaf {hdl metric scope test rows_var path parent_source} {
    upvar $rows_var rows
    set typ [cov_get_str $hdl npiCovType]
    set name [cov_get_str $hdl npiCovName]
    set full_name [cov_get_str $hdl npiCovFullName]
    if {$full_name eq ""} {set full_name $name}
    set next_path $path
    append_code_path $metric $typ $hdl $test $name $full_name next_path
    set own_source [source_dict $typ $name $full_name $hdl $test]
    if {$own_source ne ""} {
        set row_source $own_source
        set child_source $own_source
    } else {
        set row_source $parent_source
        set child_source $parent_source
    }
    set row [row_base $metric $typ $scope $name $full_name $hdl $test $row_source $next_path]
    if {$row ne ""} {
        lappend rows [append_inherited_source $row $row_source $own_source]
    }
    foreach child [cov_iter_children $hdl npiCovChild] {
        walk_code_leaf $child $metric $scope $test rows $next_path $child_source
    }
}

proc functional_scope {covergroup} {
    if {$covergroup eq ""} {return "__JSON_NULL__"}
    set idx [string first "::" $covergroup]
    if {$idx >= 0} {
        set prefix [string range $covergroup 0 [expr {$idx - 1}]]
        if {[string first "." $prefix] >= 0} {return $prefix}
        return "__JSON_NULL__"
    }
    set dot [string last "." $covergroup]
    if {$dot > 0} {return [string range $covergroup 0 [expr {$dot - 1}]]}
    return "__JSON_NULL__"
}

proc functional_full_name {path fallback} {
    set parts {}
    foreach key {covergroup coverpoint cross bin} {
        if {[dict exists $path $key]} {
            set value [dict get $path $key]
            if {$value ne ""} {lappend parts $value}
        }
    }
    if {[llength $parts] > 0} {return [join $parts "."]}
    return $fallback
}

proc walk_functional_leaf {hdl test rows_var path scope_filter parent_source} {
    upvar $rows_var rows
    set typ [cov_get_str $hdl npiCovType]
    set name [cov_get_str $hdl npiCovName]
    set next_path $path
    if {$typ eq "npiCovCovergroup" || $typ eq "npiCovCoverInstance"} {
        set next_path [dict create covergroup $name]
    } elseif {$typ eq "npiCovCoverpoint"} {
        dict set next_path coverpoint $name
    } elseif {$typ eq "npiCovCross"} {
        dict set next_path cross $name
    } elseif {$typ eq "npiCovCoverBin"} {
        dict set next_path bin $name
    }
    set full_name [functional_full_name $next_path [cov_get_str $hdl npiCovFullName]]
    set covergroup ""
    if {[dict exists $next_path covergroup]} {
        set covergroup [dict get $next_path covergroup]
    }
    set scope [functional_scope $covergroup]
    set own_source [source_dict $typ $name $full_name $hdl $test]
    if {$own_source ne ""} {
        set row_source $own_source
        set child_source $own_source
    } else {
        set row_source $parent_source
        set child_source $parent_source
    }
    set selected 0
    if {$scope_filter eq ""} {
        set selected 1
    } elseif {$scope ne "__JSON_NULL__" && [string first $scope_filter $scope] == 0} {
        set selected 1
    } elseif {[string first $scope_filter $full_name] == 0} {
        set selected 1
    }
    set path_pairs {}
    foreach key {covergroup coverpoint cross bin} {
        if {[dict exists $next_path $key]} {
            lappend path_pairs $key [json_string [dict get $next_path $key]]
        }
    }
    if {![dict exists $next_path cross]} {lappend path_pairs cross null}
    if {$selected} {
        set row [row_base functional $typ $scope $name $full_name $hdl $test $row_source $path_pairs]
        if {$row ne ""} {
            lappend rows [append_inherited_source $row $row_source $own_source]
        }
    }
    foreach child [cov_iter_children $hdl npiCovChild] {
        walk_functional_leaf $child $test rows $next_path $scope_filter $child_source
    }
}

proc metric_type {metric} {
    switch -- $metric {
        line {return npiCovLineMetric}
        toggle {return npiCovToggleMetric}
        branch {return npiCovBranchMetric}
        condition {return npiCovConditionMetric}
        fsm {return npiCovFsmMetric}
        assert {return npiCovAssertMetric}
        functional {return npiCovTestbenchMetric}
        power {return npiCovPowerMetric}
        default {return ""}
    }
}

proc walk_scope_rows {inst rows_var} {
    upvar $rows_var rows
    set full_name [cov_get_str $inst npiCovFullName]
    if {$full_name eq ""} {set full_name [cov_get_str $inst npiCovName]}
    set name [cov_get_str $inst npiCovName]
    if {$name eq ""} {set name [basename_of $full_name ""]}
    lappend rows [json_object_raw [list \
        name [json_string $name] \
        full_name [json_string $full_name] \
        parent [json_value [parent_scope $full_name]] \
        depth [depth_of $full_name] \
        type [json_string [cov_get_str $inst npiCovType]] \
        def_name [json_string [cov_get_str $inst npiCovDefName]] \
        evidence [evidence_json $inst ""]]]
    foreach child [cov_iter_children $inst npiCovInstance] {
        walk_scope_rows $child rows
    }
}

proc open_db {} {
    set vdb [env_or_empty KCOV_TCL_VDB]
    if {$vdb eq ""} {
        fail_data "VDB_OPEN_FAILED" "KCOV_TCL_VDB is required"
        return ""
    }
    if {[catch {npi_cov_open -dir $vdb} db]} {
        fail_data "VDB_OPEN_FAILED" $db
        return ""
    }
    if {$db eq ""} {
        fail_data "VDB_OPEN_FAILED" "npi_cov_open returned empty handle"
        return ""
    }
    return $db
}

proc test_handles {db} {
    set tests {}
    foreach test [cov_iter_children $db npiCovTest] {
        lappend tests $test
    }
    return $tests
}

proc merged_test {tests} {
    set merged ""
    foreach test $tests {
        if {$merged eq ""} {
            set merged $test
        } else {
            if {[catch {npi_cov_merge_test -dest $merged -src $test} next]} {
                set next ""
            }
            if {$next ne ""} {set merged $next}
        }
    }
    return $merged
}

proc selected_test {db tests} {
    set wanted [env_or_empty KCOV_TCL_TEST]
    if {$wanted eq "" || $wanted eq "merged"} {return [merged_test $tests]}
    foreach test $tests {
        if {[cov_get_str $test npiCovName] eq $wanted} {return $test}
    }
    if {[catch {npi_cov_test_by_name -name $wanted -db $db} by_name]} {
        set by_name ""
    }
    return $by_name
}

proc tests_list_action {db tests} {
    set rows {}
    foreach test $tests {
        lappend rows [json_object [list name [cov_get_str $test npiCovName]]]
    }
    ok_data [list items [json_array_raw $rows]]
}

proc scope_list_action {db} {
    set rows {}
    foreach inst [cov_iter_children $db npiCovInstance] {
        walk_scope_rows $inst rows
    }
    ok_data [list items [json_array_raw $rows]]
}

proc items_action {db tests} {
    set rows {}
    set test [selected_test $db $tests]
    if {$test eq ""} {
        fail_data "TEST_NOT_FOUND" "test not found"
        return
    }
    set wanted [metric_list]
    set scope_filter [env_or_empty KCOV_TCL_SCOPE]
    set functional_only [env_flag KCOV_TCL_FUNCTIONAL_ONLY]
    foreach inst [cov_iter_children $db npiCovInstance] {
        set inst_full [cov_get_str $inst npiCovFullName]
        if {$inst_full eq ""} {set inst_full [cov_get_str $inst npiCovName]}
        set scope_ok 0
        if {$scope_filter eq "" || [string first $scope_filter $inst_full] == 0} {
            set scope_ok 1
        }
        if {$scope_ok && !$functional_only} {
            foreach metric $wanted {
                if {$metric eq "functional"} {continue}
                set mt [metric_type $metric]
                if {$mt eq ""} {continue}
                set metric_hdl [cov_handle $inst $mt]
                if {$metric_hdl ne ""} {
                    foreach child [cov_iter_children $metric_hdl npiCovChild] {
                        walk_code_leaf $child $metric $inst_full $test rows [dict create] ""
                    }
                }
            }
        }
    }
    if {[lsearch -exact $wanted functional] >= 0} {
        set metric_hdl [cov_handle $test npiCovTestbenchMetric]
        if {$metric_hdl ne ""} {
            foreach child [cov_iter_children $metric_hdl npiCovChild] {
                walk_functional_leaf $child $test rows [dict create] $scope_filter ""
            }
        }
    }
    ok_data [list items [json_array_raw $rows]]
}

proc main {} {
    source_l1
    set action [env_or_empty KCOV_TCL_ACTION]
    set db [open_db]
    if {$db eq ""} {return}
    set tests [test_handles $db]
    if {$action eq "tests.list"} {
        tests_list_action $db $tests
    } elseif {$action eq "scope.list"} {
        scope_list_action $db
    } elseif {$action eq "items"} {
        items_action $db $tests
    } else {
        fail_data "NOT_IMPLEMENTED" "Tcl NPI coverage backend does not implement action: $action"
    }
    catch {npi_cov_close -db $db}
}

if {[catch {main} err opts]} {
    if {[catch {dict get $opts -errorinfo} info]} {
        fail_data "TCL_NPI_ERROR" $err
    } else {
        fail_data "TCL_NPI_ERROR" "$err\n$info"
    }
}
if {[llength [info commands debExit]]} {
    debExit
} else {
    exit
}
