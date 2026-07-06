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
    set out "{"
    set first 1
    foreach {k v} $pairs {
        if {!$first} {append out ","}
        set first 0
        append out [json_string $k] ":"
        append out [json_value $v]
    }
    append out "}"
    return $out
}

proc json_object_raw {pairs} {
    set out "{"
    set first 1
    foreach {k v} $pairs {
        if {!$first} {append out ","}
        set first 0
        append out [json_string $k] ":"
        append out $v
    }
    append out "}"
    return $out
}

proc write_response_raw {json_text} {
    set fp [open $::env(XDEBUG_TCL_RESPONSE_JSON) w]
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

proc safe_get_str {hdl prop} {
    if {$hdl eq ""} {return ""}
    if {[catch {npi_get_str -property $prop -object $hdl} v]} {return ""}
    return $v
}

proc safe_get {hdl prop} {
    if {$hdl eq ""} {return ""}
    if {[catch {npi_get -property $prop -object $hdl} v]} {return ""}
    return $v
}

proc safe_expr_decompile {hdl} {
    if {$hdl eq ""} {return ""}
    if {[llength [info commands ::npi_L1::npi_expr_decompile]]} {
        if {![catch {::npi_L1::npi_expr_decompile $hdl} v]} {return $v}
    }
    if {[llength [info commands npi_expr_decompile]]} {
        if {![catch {npi_expr_decompile -object $hdl} v]} {return $v}
    }
    return ""
}

proc handle_json {hdl} {
    set pairs [list \
        handle $hdl \
        name [safe_get_str $hdl npiName] \
        full_name [safe_get_str $hdl npiFullName] \
        type [safe_get_str $hdl npiType] \
        file [safe_get_str $hdl npiFile] \
        line [safe_get $hdl npiLineNo] \
        decompiled [safe_expr_decompile $hdl]]
    return [json_object $pairs]
}

proc trace_action {mode signal} {
    if {$signal eq ""} {
        fail_data "MISSING_FIELD" "args.signal is required"
        return
    }
    set handles {}
    if {$mode eq "load"} {
        set count [::npi_L1::npi_trace_load $signal handles]
    } else {
        set count [::npi_L1::npi_trace_driver $signal handles]
    }
    set arr {}
    foreach h $handles {
        lappend arr [handle_json $h]
        catch {npi_release_handle -object $h}
    }
    set status [expr {$count > 0 ? "ok" : "not_found"}]
    ok_data [list \
        signal [json_string $signal] \
        mode [json_string $mode] \
        status [json_string $status] \
        count $count \
        handles [json_array_raw $arr] \
        summary [json_object [list signal $signal mode $mode count $count status $status]]]
}

proc resolve_action {signal} {
    if {$signal eq ""} {
        fail_data "MISSING_FIELD" "args.signal is required"
        return
    }
    set h [npi_handle_by_name -name $signal -scope ""]
    if {$h eq ""} {
        fail_data "SIGNAL_NOT_FOUND" "signal not found: $signal"
        return
    }
    set full [safe_get_str $h npiFullName]
    if {$full eq ""} {set full $signal}
    set data [handle_json $h]
    catch {npi_release_handle -object $h}
    ok_data [list \
        query [json_string $signal] \
        canonical_signal [json_string $full] \
        rtl_path [json_string $full] \
        resolved $data \
        summary [json_object [list query $signal canonical_signal $full]]]
}

proc canonicalize_action {signal} {
    if {$signal eq ""} {
        fail_data "MISSING_FIELD" "args.signal is required"
        return
    }
    set h [npi_handle_by_name -name $signal -scope ""]
    if {$h eq ""} {
        fail_data "SIGNAL_NOT_FOUND" "signal not found: $signal"
        return
    }
    set full [safe_get_str $h npiFullName]
    if {$full eq ""} {set full $signal}
    set leaf [safe_get_str $h npiName]
    catch {npi_release_handle -object $h}
    ok_data [list \
        query [json_string $signal] \
        canonical [json_string $full] \
        rtl_path [json_string $full] \
        leaf [json_string $leaf] \
        ambiguous false \
        aliases [] \
        fsdb_candidates [] \
        port_mappings [] \
        summary [json_object [list query $signal ambiguous __JSON_FALSE__]]]
}

proc fsdb_format {fmt} {
    set f [string tolower $fmt]
    if {$f eq "bin" || $f eq "binary" || $f eq "b"} {return npiFsdbBinStrVal}
    if {$f eq "dec" || $f eq "decimal" || $f eq "d"} {return npiFsdbDecStrVal}
    return npiFsdbHexStrVal
}

proc fsdb_radix_char {fmt} {
    set f [string tolower $fmt]
    if {$f eq "bin" || $f eq "binary" || $f eq "b"} {return "b"}
    if {$f eq "dec" || $f eq "decimal" || $f eq "d"} {return "d"}
    return "h"
}

proc parse_fsdb_time {file_hdl time default_kind out_name} {
    upvar 1 $out_name fsdb_time
    if {$time eq ""} {
        if {$default_kind eq "max"} {
            set fsdb_time [npi_fsdb_max_time -file $file_hdl]
        } else {
            set fsdb_time [npi_fsdb_min_time -file $file_hdl]
        }
        return 1
    }
    if {$time eq "min"} {
        set fsdb_time [npi_fsdb_min_time -file $file_hdl]
        return 1
    }
    if {$time eq "max"} {
        set fsdb_time [npi_fsdb_max_time -file $file_hdl]
        return 1
    }
    if {![regexp {^([0-9]+(?:\.[0-9]+)?)([a-zA-Z]+)$} $time -> tv tu]} {
        return 0
    }
    set converted [::npi_L1::npi_fsdb_convert_time_in $file_hdl $tv $tu]
    if {$converted eq ""} {return 0}
    set fsdb_time $converted
    return 1
}

proc safe_fsdb_sig_prop_str {sig prop} {
    if {$sig eq ""} {return ""}
    if {[catch {npi_fsdb_sig_property_str -sig $sig -type $prop} v]} {return ""}
    return $v
}

proc safe_fsdb_sig_prop {sig prop} {
    if {$sig eq ""} {return ""}
    if {[catch {npi_fsdb_sig_property -sig $sig -type $prop} v]} {return ""}
    return $v
}

proc signal_info_action {fsdb signal} {
    if {$fsdb eq ""} {
        fail_data "RESOURCE_REQUIRED" "target.fsdb is required"
        return
    }
    if {$signal eq ""} {
        fail_data "MISSING_FIELD" "args.signal is required"
        return
    }
    set file_hdl [npi_fsdb_open -name $fsdb]
    if {$file_hdl eq ""} {
        fail_data "FSDB_OPEN_FAILED" "failed to open FSDB: $fsdb"
        return
    }
    set sig_hdl [npi_fsdb_sig_by_name -file $file_hdl -name $signal -scope ""]
    if {$sig_hdl eq ""} {
        catch {npi_fsdb_close -file $file_hdl}
        fail_data "SIGNAL_NOT_FOUND" "signal not found: $signal"
        return
    }
    set full [safe_fsdb_sig_prop_str $sig_hdl npiFsdbSigFullName]
    if {$full eq ""} {set full $signal}
    set name [safe_fsdb_sig_prop_str $sig_hdl npiFsdbSigName]
    set type [safe_fsdb_sig_prop_str $sig_hdl npiFsdbSigType]
    set bit_size [safe_fsdb_sig_prop $sig_hdl npiFsdbSigBitSize]
    set min_time [npi_fsdb_min_time -file $file_hdl]
    set max_time [npi_fsdb_max_time -file $file_hdl]
    set scale_unit [npi_fsdb_file_property_str -file $file_hdl -type npiFsdbFileScaleUnit]
    catch {npi_fsdb_close -file $file_hdl}
    ok_data [list \
        signal [json_string $signal] \
        full_name [json_string $full] \
        name [json_string $name] \
        type [json_string $type] \
        bit_size [json_string $bit_size] \
        min_time $min_time \
        max_time $max_time \
        scale_unit [json_string $scale_unit] \
        summary [json_object [list signal $signal full_name $full]]]
}

proc value_at_action {fsdb signal time fmt} {
    if {$fsdb eq ""} {
        fail_data "RESOURCE_REQUIRED" "target.fsdb is required"
        return
    }
    if {$signal eq "" || $time eq ""} {
        fail_data "MISSING_FIELD" "args.signal and args.time are required"
        return
    }
    set file_hdl [npi_fsdb_open -name $fsdb]
    if {$file_hdl eq ""} {
        fail_data "FSDB_OPEN_FAILED" "failed to open FSDB: $fsdb"
        return
    }
    if {![regexp {^([0-9]+(?:\.[0-9]+)?)([a-zA-Z]+)$} $time -> tv tu]} {
        catch {npi_fsdb_close -file $file_hdl}
        fail_data "TIME_SPEC_INVALID" "failed to parse time: $time"
        return
    }
    set fsdb_time [::npi_L1::npi_fsdb_convert_time_in $file_hdl $tv $tu]
    if {$fsdb_time eq ""} {
        catch {npi_fsdb_close -file $file_hdl}
        fail_data "TIME_SPEC_INVALID" "failed to convert time: $time"
        return
    }
    set format [fsdb_format $fmt]
    set raw [::npi_L1::npi_fsdb_sig_value_at $file_hdl $signal $fsdb_time $format]
    if {$raw eq ""} {
        catch {npi_fsdb_close -file $file_hdl}
        fail_data "SIGNAL_NOT_FOUND" "failed to read value: $signal"
        return
    }
    set radix [fsdb_radix_char $fmt]
    catch {npi_fsdb_close -file $file_hdl}
    ok_data [list \
        signal [json_string $signal] \
        time [json_string $time] \
        fsdb_time $fsdb_time \
        raw [json_string $raw] \
        radix [json_string $radix] \
        status [json_string "ok"] \
        summary [json_object [list signal $signal time $time status ok]]]
}

proc value_batch_at_action {fsdb signals time fmt} {
    if {$fsdb eq ""} {
        fail_data "RESOURCE_REQUIRED" "target.fsdb is required"
        return
    }
    if {[llength $signals] == 0 || $time eq ""} {
        fail_data "MISSING_FIELD" "args.signals[] and args.time are required"
        return
    }
    set file_hdl [npi_fsdb_open -name $fsdb]
    if {$file_hdl eq ""} {
        fail_data "FSDB_OPEN_FAILED" "failed to open FSDB: $fsdb"
        return
    }
    if {![regexp {^([0-9]+(?:\.[0-9]+)?)([a-zA-Z]+)$} $time -> tv tu]} {
        catch {npi_fsdb_close -file $file_hdl}
        fail_data "TIME_SPEC_INVALID" "failed to parse time: $time"
        return
    }
    set fsdb_time [::npi_L1::npi_fsdb_convert_time_in $file_hdl $tv $tu]
    set format [fsdb_format $fmt]
    set radix [fsdb_radix_char $fmt]
    set arr {}
    set missing 0
    foreach sig $signals {
        set raw [::npi_L1::npi_fsdb_sig_value_at $file_hdl $sig $fsdb_time $format]
        if {$raw eq ""} {
            incr missing
            lappend arr [json_object_raw [list signal [json_string $sig] time [json_string $time] status [json_string "signal_not_found"] value null raw null]]
        } else {
            lappend arr [json_object_raw [list signal [json_string $sig] time [json_string $time] status [json_string "ok"] raw [json_string $raw] radix [json_string $radix]]]
        }
    }
    catch {npi_fsdb_close -file $file_hdl}
    ok_data [list \
        time [json_string $time] \
        fsdb_time $fsdb_time \
        values [json_array_raw $arr] \
        summary [json_object [list time $time signal_count [llength $signals] missing_count $missing]]]
}

proc signal_scan_action {fsdb signal begin_time end_time fmt max_rows} {
    if {$fsdb eq ""} {
        fail_data "RESOURCE_REQUIRED" "target.fsdb is required"
        return
    }
    if {$signal eq ""} {
        fail_data "MISSING_FIELD" "args.signal is required"
        return
    }
    set file_hdl [npi_fsdb_open -name $fsdb]
    if {$file_hdl eq ""} {
        fail_data "FSDB_OPEN_FAILED" "failed to open FSDB: $fsdb"
        return
    }
    set sig_hdl [npi_fsdb_sig_by_name -file $file_hdl -name $signal -scope ""]
    if {$sig_hdl eq ""} {
        catch {npi_fsdb_close -file $file_hdl}
        fail_data "SIGNAL_NOT_FOUND" "signal not found: $signal"
        return
    }
    if {![parse_fsdb_time $file_hdl $begin_time min begin_fsdb]} {
        catch {npi_fsdb_close -file $file_hdl}
        fail_data "TIME_SPEC_INVALID" "failed to parse begin time: $begin_time"
        return
    }
    if {![parse_fsdb_time $file_hdl $end_time max end_fsdb]} {
        catch {npi_fsdb_close -file $file_hdl}
        fail_data "TIME_SPEC_INVALID" "failed to parse end time: $end_time"
        return
    }
    if {$max_rows eq "" || $max_rows <= 0} {set max_rows 200}
    set format [fsdb_format $fmt]
    set radix [fsdb_radix_char $fmt]
    set vct_hdl [npi_fsdb_create_vct -sig $sig_hdl]
    if {$vct_hdl eq ""} {
        catch {npi_fsdb_close -file $file_hdl}
        fail_data "VCT_CREATE_FAILED" "failed to create value-change traversal for: $signal"
        return
    }
    set ok [npi_fsdb_goto_time -vct $vct_hdl -time $begin_fsdb]
    if {$ok == 0} {
        set ok [npi_fsdb_goto_first -vct $vct_hdl]
    }
    set arr {}
    set truncated "__JSON_FALSE__"
    set count 0
    while {$ok != 0} {
        set t [npi_fsdb_vct_time -vct $vct_hdl]
        if {$t < $begin_fsdb} {
            set ok [npi_fsdb_goto_next -vct $vct_hdl]
            continue
        }
        if {$t > $end_fsdb} {break}
        set raw [npi_fsdb_vct_value -vct $vct_hdl -format $format]
        lappend arr [json_object_raw [list time $t raw [json_string $raw] radix [json_string $radix]]]
        incr count
        if {$count >= $max_rows} {
            set next_ok [npi_fsdb_goto_next -vct $vct_hdl]
            if {$next_ok != 0} {set truncated "__JSON_TRUE__"}
            break
        }
        set ok [npi_fsdb_goto_next -vct $vct_hdl]
    }
    catch {npi_fsdb_release_vct -vct $vct_hdl}
    catch {npi_fsdb_close -file $file_hdl}
    ok_data [list \
        signal [json_string $signal] \
        begin_time [json_string $begin_time] \
        end_time [json_string $end_time] \
        begin_fsdb $begin_fsdb \
        end_fsdb $end_fsdb \
        radix [json_string $radix] \
        changes [json_array_raw $arr] \
        truncated [json_value $truncated] \
        summary [json_object [list signal $signal change_count $count truncated $truncated]]]
}

proc scope_list_action {fsdb path max_depth max_rows} {
    if {$fsdb eq ""} {
        fail_data "RESOURCE_REQUIRED" "target.fsdb is required"
        return
    }
    set file_hdl [npi_fsdb_open -name $fsdb]
    if {$file_hdl eq ""} {
        fail_data "FSDB_OPEN_FAILED" "failed to open FSDB: $fsdb"
        return
    }
    set scopes {}
    set signals {}
    if {$path eq ""} {
        set scope_iter [npi_fsdb_iter_top_scope -file $file_hdl]
    } else {
        set root [npi_fsdb_scope_by_name -file $file_hdl -name $path -scope ""]
        if {$root eq ""} {
            catch {npi_fsdb_close -file $file_hdl}
            fail_data "SCOPE_NOT_FOUND" "scope not found: $path"
            return
        }
        set scope_iter [npi_fsdb_iter_child_scope -scope $root]
    }
    while {$scope_iter ne ""} {
        set s [npi_fsdb_iter_scope_next -iter $scope_iter]
        if {$s eq ""} {break}
        lappend scopes [npi_fsdb_scope_property_str -scope $s -type npiFsdbScopeFullName]
        if {[llength $scopes] >= $max_rows} {break}
    }
    if {$scope_iter ne ""} {catch {npi_fsdb_iter_scope_stop -iter $scope_iter}}
    set sig_scope ""
    if {$path ne ""} {set sig_scope [npi_fsdb_scope_by_name -file $file_hdl -name $path -scope ""]}
    if {$path eq ""} {
        set sig_iter [npi_fsdb_iter_top_sig -file $file_hdl]
    } elseif {$sig_scope ne ""} {
        set sig_iter [npi_fsdb_iter_sig -scope $sig_scope]
    } else {
        set sig_iter ""
    }
    while {$sig_iter ne ""} {
        set sig [npi_fsdb_iter_sig_next -iter $sig_iter]
        if {$sig eq ""} {break}
        lappend signals [npi_fsdb_sig_property_str -sig $sig -type npiFsdbSigFullName]
        if {[llength $signals] >= $max_rows} {break}
    }
    if {$sig_iter ne ""} {catch {npi_fsdb_iter_sig_stop -iter $sig_iter}}
    catch {npi_fsdb_close -file $file_hdl}
    ok_data [list \
        path [json_string $path] \
        scopes [json_array $scopes] \
        signals [json_array $signals] \
        signals_preview [json_array $signals] \
        summary [json_object [list path $path scope_count [llength $scopes] signal_count [llength $signals]]]]
}

proc active_trace_action {signal time} {
    if {$signal eq "" || $time eq ""} {
        fail_data "MISSING_FIELD" "args.signal and args.requested_time are required"
        return
    }
    set result {}
    set rc 0
    set call_error ""
    if {[catch {set rc [::npi_L1::npi_active_trace_driver $signal result $time]} call_error]} {
        set rc 0
        set result {}
    }
    set active_time ""
    if {[llength $result] >= 1} {
        set active_time [lindex $result 0]
    }
    set arr {}
    foreach item $result {
        lappend arr [json_string $item]
    }
    set dump_text ""
    set dump_rc 0
    set dump_error ""
    set dump_path [file join [pwd] "xdebug_active_trace_dump_[pid].txt"]
    if {[catch {
        set fp [open $dump_path w]
        set dump_rc [::npi_L1::npi_active_trace_driver_dump $signal $fp $time]
        close $fp
        set fp [open $dump_path r]
        set dump_text [read $fp]
        close $fp
        file delete -force $dump_path
    } dump_error]} {
        catch {close $fp}
        catch {file delete -force $dump_path}
        set dump_text ""
        set dump_rc 0
    }
    ok_data [list \
        signal [json_string $signal] \
        requested_time [json_string $time] \
        active_time [json_string $active_time] \
        status [json_string [expr {($rc > 0 || $dump_rc > 0 || $active_time ne "") ? "ok" : "not_found"}]] \
        active_call_rc $rc \
        active_call_error [json_string $call_error] \
        dump_rc $dump_rc \
        dump_error [json_string $dump_error] \
        active_dump [json_string $dump_text] \
        raw [json_array_raw $arr] \
        summary [json_object [list signal $signal requested_time $time active_time $active_time status [expr {($rc > 0 || $dump_rc > 0 || $active_time ne "") ? "ok" : "not_found"}]]]]
}

proc main {} {
    source_l1
    set action [env_or_empty XDEBUG_TCL_ACTION]
    if {$action eq "trace.driver"} {
        trace_action driver [env_or_empty XDEBUG_TCL_SIGNAL]
    } elseif {$action eq "trace.load" || $action eq "trace.query"} {
        set mode [env_or_empty XDEBUG_TCL_TRACE_MODE]
        if {$mode eq ""} {set mode load}
        trace_action $mode [env_or_empty XDEBUG_TCL_SIGNAL]
    } elseif {$action eq "signal.resolve"} {
        resolve_action [env_or_empty XDEBUG_TCL_SIGNAL]
    } elseif {$action eq "signal.canonicalize"} {
        canonicalize_action [env_or_empty XDEBUG_TCL_SIGNAL]
    } elseif {$action eq "signal.info"} {
        signal_info_action [env_or_empty XDEBUG_TCL_FSDB] [env_or_empty XDEBUG_TCL_SIGNAL]
    } elseif {$action eq "signal.scan"} {
        signal_scan_action [env_or_empty XDEBUG_TCL_FSDB] [env_or_empty XDEBUG_TCL_SIGNAL] [env_or_empty XDEBUG_TCL_BEGIN] [env_or_empty XDEBUG_TCL_END] [env_or_empty XDEBUG_TCL_FORMAT] [env_or_empty XDEBUG_TCL_MAX_ROWS]
    } elseif {$action eq "value.at"} {
        value_at_action [env_or_empty XDEBUG_TCL_FSDB] [env_or_empty XDEBUG_TCL_SIGNAL] [env_or_empty XDEBUG_TCL_TIME] [env_or_empty XDEBUG_TCL_FORMAT]
    } elseif {$action eq "value.batch_at"} {
        value_batch_at_action [env_or_empty XDEBUG_TCL_FSDB] [split [env_or_empty XDEBUG_TCL_SIGNALS] "\n"] [env_or_empty XDEBUG_TCL_TIME] [env_or_empty XDEBUG_TCL_FORMAT]
    } elseif {$action eq "scope.list"} {
        scope_list_action [env_or_empty XDEBUG_TCL_FSDB] [env_or_empty XDEBUG_TCL_SCOPE] [env_or_empty XDEBUG_TCL_MAX_DEPTH] [env_or_empty XDEBUG_TCL_MAX_ROWS]
    } elseif {$action eq "trace.active_driver" || $action eq "trace.active_driver_chain"} {
        active_trace_action [env_or_empty XDEBUG_TCL_SIGNAL] [env_or_empty XDEBUG_TCL_TIME]
    } else {
        fail_data "NOT_IMPLEMENTED" "Tcl NPI backend does not implement action: $action"
    }
}

if {[catch {main} err opts]} {
    if {[catch {dict get $opts -errorinfo} info]} {
        fail_data "TCL_NPI_ERROR" $err
    } else {
        fail_data "TCL_NPI_ERROR" "$err\n$info"
    }
}
debExit
