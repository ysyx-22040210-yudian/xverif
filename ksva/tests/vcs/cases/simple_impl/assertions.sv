// Test case: simple_impl — basic |-> implication
// ksva golden IR source

property p_simple;
  @(posedge clk) disable iff (!rst_n)
  req |-> ack;
endproperty

a_simple: assert property (p_simple);
