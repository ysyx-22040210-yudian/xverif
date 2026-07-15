`ifndef KVERIF_KLOC_REPORT_SERVER_SV
`define KVERIF_KLOC_REPORT_SERVER_SV

class kloc_report_server extends uvm_default_report_server;

  static int next_id = 1;
  static string loc_cache[string];  // "file:line:msg_id" -> "L_XXXXXXXX"
  static int map_fd = 0;

  protected string map_path = "sim.log.kloc.jsonl";

  function string get_loc_id(string file, int line, string msg_id);
    string key = $sformatf("%s:%0d:%s", file, line, msg_id);
    if (!loc_cache.exists(key)) begin
      loc_cache[key] = $sformatf("L_%08X", next_id);
      next_id++;
      write_jsonl_entry(loc_cache[key], file, line, msg_id);
    end
    return loc_cache[key];
  endfunction

  function void write_jsonl_entry(string loc_id, string file, int line, string msg_id);
    if (map_fd == 0) begin
      map_fd = $fopen(map_path, "a");
    end
    $fwrite(map_fd, "{\"loc_id\":\"%s\",\"file\":\"%s\",\"line\":%0d,\"msg_id\":\"%s\"}\n",
            loc_id, file, line, msg_id);
    $fflush(map_fd);
  endfunction

  function void set_map_path(string path);
    if (map_fd != 0) begin
      $fclose(map_fd);
      map_fd = 0;
    end
    map_path = path;
  endfunction

  virtual function string compose_report_message(uvm_report_message report_message,
                                                 string report_object_name = "");

    string sev_string;
    uvm_severity l_severity;
    uvm_verbosity l_verbosity;
    string filename_line_string;
    string time_str;
    string line_str;
    string context_str;
    string verbosity_str;
    string terminator_str;
    string msg_body_str;
    uvm_report_message_element_container el_container;
    string prefix;
    uvm_report_handler l_report_handler;

    l_severity = report_message.get_severity();
    sev_string = l_severity.name();

    if (report_message.get_filename() != "") begin
      filename_line_string = {get_loc_id(report_message.get_filename(),
                                         report_message.get_line(),
                                         report_message.get_id()), " "};
    end

    //SNPS_ADDED_CODE_BEGIN
    //TYPE:Enhancement
    //INFO:To give user flexibilty to print realtime in report messages
    `ifdef UVM_USE_REALTIME_IN_MSGS
        $swrite(time_str, "%0t", $realtime);
    `else
        $swrite(time_str, "%0t", $time);
    `endif
    //SNPS_ADDED_CODE_END
    if (report_message.get_context() != "")
      context_str = {"@@", report_message.get_context()};

    if (show_verbosity) begin
      if ($cast(l_verbosity, report_message.get_verbosity()))
        verbosity_str = l_verbosity.name();
      else
        verbosity_str.itoa(report_message.get_verbosity());
      verbosity_str = {"(", verbosity_str, ")"};
    end

    if (show_terminator)
      terminator_str = {" -",sev_string};

    el_container = report_message.get_element_container();
    if (el_container.size() == 0)
      msg_body_str = report_message.get_message();
    else begin
      prefix = uvm_default_printer.knobs.prefix;
      uvm_default_printer.knobs.prefix = " +";
      msg_body_str = {report_message.get_message(), "\n", el_container.sprint()};
      uvm_default_printer.knobs.prefix = prefix;
    end

    if (report_object_name == "") begin
      l_report_handler = report_message.get_report_handler();
      report_object_name = l_report_handler.get_full_name();
    end

    compose_report_message = {sev_string, verbosity_str, " ", filename_line_string, "@ ",
      time_str, ": ", report_object_name, context_str,
      " [", report_message.get_id(), "] ", msg_body_str, terminator_str};

  endfunction

endclass

`endif
