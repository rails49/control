# The look rules' values, copied in

`tokens.css` beside this file is a verbatim copy of `docs/tokens.css` in
[rails49/.github](https://github.com/rails49/.github/blob/main/docs/tokens.css),
which is where the look rules' values live
([ADR-0005](https://github.com/rails49/.github/blob/main/docs/adr/0005-the-look-rules-travel-as-a-copied-file-not-a-package.md)).
What each token means and who is bound by it is
[LOOK.md](https://github.com/rails49/.github/blob/main/docs/LOOK.md) beside it
there.

    source   rails49/.github, docs/tokens.css
    commit   c91e9bea6680808edab65675998ab49ea6309cd3
    copied   2026-09-21, from that repository at 710f23fe

The commit is the pin: the one that last wrote the file, so that diffing this
copy against it is a diff of the same thing. Nothing is installed and nothing
is fetched: a change over there arrives as an issue here, and taking it is
copying the file again and moving those lines.

**The copy is inert.** Nothing imports it and no build reads it. This app holds
the same values in its own form — `src/render/units.ts` holds every colour it
draws with, and `RAIL_BUTTON_PX` and `RAIL_TURNS_PX` beside them — and
`test/styles.test.ts` asserts that what it draws with equals what is here.
ADR-0003 leaves how a UI expresses a value free, and holding every colour in
one file is a good reason not to link a second stylesheet.

The test never reaches the network, so it cannot go red on someone else's
commit; it goes red on an edit here, which is the one thing it is for. The day
a new copy lands with a value this app has not followed yet, it goes red until
the code follows.

**It runs in the ordinary gate**, which is where the assertions the issue asked
for already live (`test/styles.test.ts`). ADR-0005 says the check runs outside
the required gate, and the reason it gives is the one that does not apply here:
a check that fetched the source could go red on somebody else's commit and
red-light every open pull request until someone synced. This one reads a file
in this repository. Keeping it out of the gate would only mean a drift that
lands.
