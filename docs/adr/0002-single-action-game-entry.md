# Single-action game entry

The primary player journey is to enter a username, choose a Minecraft version,
and use one action that installs the selected version when needed and launches
the game. Separate installation and play buttons make players manage preparation
steps themselves and create more opportunities for mistakes; the launcher owns
that sequencing.

Keep username, version selection, and the single launch action together in a
compact primary control bar, following the supplied launcher reference. Save
the username automatically without a separate save button. Memory allocation
belongs in Settings, with automatic saving there as well, rather than on the
main screen. Use a smaller default window with a modest Minecraft backdrop
and no news or changelog feed. Show installation progress and errors directly
above the bottom launch bar. The single button is labeled Play and owns
installation and launch. The approved visual reference is prototype layout A:
a quiet block landscape above a solid charcoal launch bar, warm white text,
green Play action, readable system typography, and subtle rounded controls.
Settings is a small secondary entry at the top. The comparison toolbar and
simulated prototype states are not product UI.

Offer stable Minecraft releases by default, initially selecting the latest
stable release on first use. Remember the username and last selected entry
across launches so returning players can immediately use Play. Expose snapshots
through an option in Settings and mark downloaded versions in the version list.

Automatically associate each Minecraft version with its own instance so worlds
and settings stay isolated across versions. Players select a version without
having to create or name an instance. This trades automatic sharing of worlds
between versions for protection against accidentally opening a newer world in
an older game version. Keep existing instances accessible as named entries in
the same selector alongside version choices, preserving access to their worlds
without a separate instance management screen.

The user approved the visual prototype. The implementation specification and
ready-for-agent ticket are published under `.scratch/launcher-ux/`.
