-- Copyright 2026 FREISA contributors
-- Solderpad Hardware License, Version 2.1, see LICENSE.md for details.
-- SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1
--
-- Info     : Blinks an LED from a free-running counter in VHDL.
-- Module   : blink
-- Author   : Christian Conti
-- Contact  : christian.conti@mail.it

library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity blink is port(clk : in std_logic; led : out std_logic); end;
architecture rtl of blink is signal c : unsigned(23 downto 0) := (others => '0'); begin
  process(clk) begin if rising_edge(clk) then c <= c + 1; end if; end process;
  led <= c(23);
end;
