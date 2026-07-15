// Test case: overlap_nonoverlap — |-> vs |=> comparison
// ksva golden IR source

property p_overlap;
  @(posedge clk) req |-> ack;
endproperty

property p_nonoverlap;
  @(posedge clk) req |=> ack;
endproperty

a_overlap: assert property (p_overlap);
a_nonoverlap: assert property (p_nonoverlap);
