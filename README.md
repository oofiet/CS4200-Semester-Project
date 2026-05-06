# CS4200 Semester Project
Each folder contains its own RISC-V simulator with a different branch prediction strategy.



**Never Take** - Never takes a branch. Horribly inefficient, although you can invert the results to see what always take would look like, which is surprisingly great in this test program.

**1-Bit Predictor** - Takes a branch only if the last branch was taken. Generally decent.

**2-Bit Predictor** - Acts as a typical 2-bit saturating predictor. Better than a 1-bit predictor for nested loops.

## Branch Stats
branch_stats.log in each folder contains the hits, misses, accuracy, and "wasted instructions." Wasted instructions occur when a valid instruction is flushed from either the IF or ID stages.

## Example Instructions
real_inst.txt contains the human-readable version of the test program used in each simulator.
