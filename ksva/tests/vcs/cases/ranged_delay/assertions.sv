// Test case: ranged_delay — ##[1:4] range delay
// ksva golden IR source

property p_ranged;
  @(posedge clk) disable iff (!rst_n)
  req |-> ##[1:4] ack;
endproperty

a_ranged: assert property (p_ranged);
