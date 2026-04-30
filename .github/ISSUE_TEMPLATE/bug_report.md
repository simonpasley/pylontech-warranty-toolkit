---
name: Bug report
about: Report a parser bug, wrong verdict, or other issue
title: ''
labels: bug
assignees: ''
---

## What were you trying to do?

<!-- e.g. "Diagnose pack 4 on a US2000C rack" -->

## What happened?

<!-- e.g. "The verdict came back HEALTHY but the spread reads 80 mV which should be FAILED" -->

## What did you expect?

<!-- The result you would have expected to see -->

## Battery info

Paste the output of the `info` command (run it from the tool's "Console" section, or read it from the raw section of the diagnostic report). If the tool can't connect, please describe your hardware: model (US3000C / US5000 / etc), approximate firmware year, and chipset of your USB-RS232 cable.

```
<paste `info` output here>
```

## Output of the failing command

If the verdict or parsing looks wrong, paste the raw output of the relevant command. The tool always shows the raw output in collapsible "Raw …" panels at the bottom of each diagnostic.

```
<paste e.g. `bat 4`, `pwr`, `stat` raw output here>
```

## Environment

- OS: <!-- macOS 14, Windows 11, Ubuntu 24.04 -->
- Python version: <!-- output of `python3 --version` -->
- Tool version / commit: <!-- output of `git rev-parse --short HEAD` if you cloned, or "downloaded zip on YYYY-MM-DD" -->
- Cable: <!-- chipset (FTDI / CH340 / CP210x / PL2303), and whether you bought it labelled as "Pylontech BMS console cable" -->

## Anything else?

<!-- Screenshots, dmesg output, stacktrace from the terminal where you ran `python app.py`, etc. -->
