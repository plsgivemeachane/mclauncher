# Version 0.1.4 package acceptance

- Artifact: `dist/mclauncher_0.1.4_amd64.deb`
- Platform: Ubuntu 24.04 amd64; built in a clean Ubuntu container with pinned dependencies.
- Size: 47,377,186 bytes
- SHA-256: `9864d0826edbdebd9ea1c29d1b99493b2257438f7e142610ad94b0f3cfb82045`
- Version metadata: mclauncher 0.1.4 amd64.
- Installed 0.1.3, then upgraded with `apt install -y /src/dist/mclauncher_0.1.4_amd64.deb`.
- Fresh dpkg-query verification: `mclauncher 0.1.4 install ok installed`.
- Installed executable launched under Xvfb, stayed running through Home / Instances navigation and resizing to 680×420.
- Visually inspected installed-home-014.png and installed-instances-014.png; bundled artwork and prominent Open Folder / Play controls render correctly.
- Source verification: 164 tests passed; Python compilation, packaging shell syntax, and git diff --check passed.
- Version script: patch/minor/major and dry-run verified against isolated fixture copies.

Install from the repository root:

```sh
sudo apt install ./dist/mclauncher_0.1.4_amd64.deb
```

For the next release, run `python3 packaging/bump-version.py` once, then build.
The build itself preserves the selected version for repeatable rebuilds.
