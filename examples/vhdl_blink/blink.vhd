library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity blink is port(clk : in std_logic; led : out std_logic); end;
architecture rtl of blink is signal c : unsigned(23 downto 0) := (others => '0'); begin
  process(clk) begin if rising_edge(clk) then c <= c + 1; end if; end process;
  led <= c(23);
end;
