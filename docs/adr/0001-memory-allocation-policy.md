# Memory allocation policy

The launcher chooses an initial game memory limit as one quarter of total
physical RAM, rounded down to whole GiB, with a minimum of 1 GiB and a maximum
of 8 GiB. This leaves the majority of memory available to Ubuntu and other
applications while giving larger machines a useful vanilla Minecraft default.

Players may save any whole-GiB value from 1 GiB through the machine's whole-GiB
physical RAM amount. The launcher validates this value immediately before
launch and passes it as separate `-Xmx<N>G` and `-Xms<N>G` JVM arguments.

Physical RAM is read with `os.sysconf("SC_PHYS_PAGES")` and
`os.sysconf("SC_PAGE_SIZE")`, so the policy does not add a runtime dependency.
