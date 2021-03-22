# vim: set syntax=gnuplot:

# A sample datafile
DATAFILE = "data.csv"

set term dumb
set grid

set xtic #rotate by 90

set style fill solid 0.66

set boxwidth 0.50
set datafile separator ","

# Define a function that maps a number to a bin:
#  startx, endx: expected interval of values for x
#  n: number of bins
bin(x, startx, endx, n) = (x > endx)? n - 1 : ((x < startx)? 0 : floor(n * ((x - startx) / (endx - startx))))

# Define a function to map bin back to a real value
start_of_bin(i, startx, endx, n) = startx + i * ((endx - startx) / n) 

N = 50 # number of bins
START = 0.0 # start of range (we are interested into)
END = 10.0 # end of range

# Configure x-axis
set xrange [0:N]
set for [i=0:N:+5] xtics (sprintf("%.1f", start_of_bin(i, START, END, N)) i)

# Plot histogram: map (multiple times) every bin to 1.0. 
# Must use smooth freq to actually count frequencies (see `help smooth freq`) !!
plot DATAFILE using (bin($1, START, END, N)):(1.0) smooth freq with boxes title "Some distribution"
