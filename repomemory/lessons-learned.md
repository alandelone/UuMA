# Lessons Learned

## Context repair before code repair

When execution loops, repeated code edits hide the actual failure. Inspect the findings record and
approved contract first. If an Agent lacked a dependency or operating fact, add that fact to the
narrowest relevant rule. If an assertion contradicts approved requirements, correct the execution
brief and document why. Resume only after the shared context is coherent.

## Recovery requires a baseline

A Git reset is not a generic restart mechanism. Without a known commit, preserved diff, and exact
scope, it is destructive rather than restorative. Record the baseline before delegating recovery.
