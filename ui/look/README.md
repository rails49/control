# The look rules' values, copied in

`tokens.css` beside this file is a verbatim copy of `docs/tokens.css` in
[rails49/.github](https://github.com/rails49/.github/blob/main/docs/tokens.css),
which is where the look rules' values live
([ADR-0005](https://github.com/rails49/.github/blob/main/docs/adr/0005-the-look-rules-travel-as-a-copied-file-not-a-package.md)).
What each token means and who is bound by it is
[LOOK.md](https://github.com/rails49/.github/blob/main/docs/LOOK.md) beside it
there.

    source   rails49/.github, docs/tokens.css
    commit   710f23fe6f04471d7d908cb85ba8db8a03a852c7
    copied   2026-09-21

The commit is the pin. Nothing is installed and nothing is fetched: a change
over there arrives as an issue here, and taking it is copying the file again
and moving that line.

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
