// Test case: rose_fell — $rose / $fell sampled functions
// ksva golden IR source

property p_rose;
  @(posedge clk)
  $rose(req) |=> ack;
endproperty

a_rose: assert property (p_rose);
