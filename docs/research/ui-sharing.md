# How two repositories share TypeScript UI code

Resolves [rails49/.github#5](https://github.com/rails49/.github/issues/5). Surveys
the mechanisms by which `control/ui` and `occupancy/ui` could share Lit
components, CSS tokens and shared config, and prices each one. No decision is
taken here.

The central question the issue asks is **whether a package can be shared
between two repositories without getting a repository of its own**. The answer
is yes, by three different routes, and one of them — a pnpm git dependency
pointing at a subdirectory — is both the least known and the closest fit. It
does not work under npm.

The secondary question is the licence boundary. `occupancy` is AGPL-3.0
(`occupancy/LICENSE`), `control` is MIT (`control/LICENSE`). No packaging
mechanism enforces anything about licences; what the mechanisms differ on is
whether the shared files end up **inside** the consumer's repository and
history, or stay outside it.

## Versions this was tested at

Claims marked *(tested)* were run on this machine on 2026-09-21:

- pnpm 11.0.4
- npm 11.6.2
- node 24.11.1
- git 2.50.1 (Apple)

pnpm's behaviour here is strongly version-dependent. Several of the facts below
changed in pnpm 9 and again in pnpm 11. Anything written against pnpm 10 or
earlier is likely to be wrong.

---

## 1. The crux: can a dependency point at a subdirectory of a repository?

This decides whether the shared package needs its own repository, because the
alternative is to keep it in a subdirectory of one of the two repositories that
already exist.

### pnpm: yes, since pnpm 9.0.0

pnpm documents a `path:` parameter on git specifiers:

> `pnpm add RexSkz/test-git-subfolder-fetch#path:/packages/simple-react-app`
>
> — <https://pnpm.io/package-sources>

Parameters combine with `&`, so a branch or a semver range can be given
alongside the path:

> `pnpm add RexSkz/test-git-subdir-fetch.git#beta&path:/packages/simple-react-app`
>
> — <https://pnpm.io/package-sources>

The feature landed in pnpm 9.0.0. Its changelog entry reads:

> It is now possible to install only a subdirectory from a Git repository.
> For example, `pnpm add github:user/repo#path:packages/foo` will add a
> dependency from the `packages/foo` subdirectory.
>
> — pnpm 9.0.0 release notes, <https://github.com/pnpm/pnpm/releases/tag/v9.0.0>
> (issue [#4765](https://github.com/pnpm/pnpm/issues/4765),
> PR [#7487](https://github.com/pnpm/pnpm/pull/7487), merged 2024-01-24)

*(tested)* Against a local repository containing `packages/foo` at version
1.2.3, `pnpm add "git+file:///…/repo#path:/packages/foo"` installed `@x/foo`
1.2.3 and wrote this lockfile entry:

```yaml
'@x/foo@git+file:///…/repo#0ed4729…&path:/packages/foo':
  resolution: {commit: 0ed4729…, path: /packages/foo, repo: file:///…/repo, type: git}
  version: 1.2.3
```

The lockfile pins an exact commit. Against GitHub, pnpm resolves the ref to a
commit SHA and fetches a `codeload.github.com` tarball of the whole repository
at that commit, then takes the subdirectory out of it *(tested)*. The whole
repository is transferred either way; only the extracted tree is scoped.

### npm: no, and it fails silently

npm's `package.json` reference documents the git URL grammar as

> `<protocol>://[<user>[:<password>]@]<hostname>[:<port>][:][/]<path>[#<commit-ish> | #semver:<semver>]`
>
> — <https://docs.npmjs.com/cli/v11/configuring-npm/package-json>

There is no subdirectory element. The request has been open since 2012
([npm/npm#2974](https://github.com/npm/npm/issues/2974), closed in 2016 without
implementation) and npm has never shipped it.

The important part is what npm does when given the pnpm syntax anyway. It does
not error. *(tested)* On the same local repository:

```
$ npm install "git+file:///…/repo#path:/packages/foo"
added 1 package in 499ms
```

What it added was the **repository root package**, `monorepo-root@0.0.0`, not
`@x/foo`. npm wrote the spec verbatim into `package.json` under the key
`monorepo-root`, and dropped the fragment entirely from the lockfile:

```json
"node_modules/monorepo-root": {
  "version": "0.0.0",
  "resolved": "git+file:///…/repo#0ed4729de314475085d96c97c05da2483afe485e"
}
```

No warning is printed. The other candidate syntaxes (`?path=`, and the
gitpkg-style `//packages/foo`) are treated as part of the repository path and
fail with `does not appear to be a git repository` *(tested)*.

So a subdirectory git dependency is a pnpm-only mechanism, and a lockfile
written by pnpm cannot be reproduced by npm. Both repositories already use
pnpm, so this is not by itself disqualifying — but it makes pnpm load-bearing
rather than a preference.

### Two traps in the pnpm mechanism

**Semver ranges match repository tags, not the package's version.** `#semver:`
selects a git ref, and in a repository holding several packages the tags belong
to the repository. *(tested)* In a repository whose tag `v2.0.0` marks a commit
where `packages/foo` is still at 1.2.3:

```
$ pnpm add "git+file:///…/repo#semver:^2.0.0&path:/packages/foo"
+ @x/foo 1.2.3
```

The range `^2.0.0` installed version 1.2.3, with no warning. `#semver:` is
therefore only safe if the repository's tags are the shared package's versions.
Pinning a branch or a commit avoids the problem entirely.

**A `prepare` script must be allowlisted under pnpm 11.** npm and pnpm both
build git dependencies: "If the package being installed contains a `prepare`
script, its `dependencies` and `devDependencies` will be installed, and the
prepare script will be run, before the package is packaged and installed"
(<https://docs.npmjs.com/cli/v11/commands/npm-install>). pnpm 11 refuses to do
that without consent *(tested)*:

```
ERR_PNPM_GIT_DEP_PREPARE_NOT_ALLOWED  Failed to prepare git-hosted package …
The git-hosted package "@x/foo@1.2.3" needs to execute build scripts but is not
in the "allowBuilds" allowlist.
```

Adding `allowBuilds: {'@x/foo': true}` to `pnpm-workspace.yaml` fixes it. The
consumer then gets the built output only, because `files` is honoured as in a
published tarball *(tested)* — `src/` was absent, `dist/` present.

The cost of that build is real. *(tested)* Installing one small package from a
subdirectory of a public monorepo pulled **1243 packages**, because the git
dependency's own `devDependencies` are installed in order to run `prepare`. A
shared package with no `prepare` script and no build avoids all of this: pnpm
installs the subdirectory as-is, with no allowlist entry and no devDependency
tree *(tested)*.

---

## 2. Mechanism by mechanism

### 2.1 Public npm registry

**Pinning.** An ordinary semver range in `dependencies`. `package-lock.json`
"describes the exact tree that was generated, such that subsequent installs are
able to generate identical trees"
(<https://docs.npmjs.com/cli/v11/configuring-npm/package-lock-json>); pnpm's
equivalent is `pnpm-lock.yaml`, and `--frozen-lockfile` defaults to true in CI
when a lockfile is present (<https://pnpm.io/cli/install>).

**Cost of a change.** Bump the version, publish, bump the range in each
consumer, commit the lockfile. A published version is permanent: "Once a
package is published with a given name and version, that specific name and
version combination can never be used again, even if it is removed with
`npm unpublish`"
(<https://docs.npmjs.com/cli/v11/commands/npm-publish>). Testing an unpublished
change needs `npm link`, `pnpm link <dir>`, or a `file:` dependency. pnpm
recommends `file:` over `link` for packages with peer dependencies, because it
"better resolves the peer dependencies" (<https://pnpm.io/cli/link>) — which is
the case for a Lit component package.

**Drift.** Silent. A consumer left on an old range keeps installing the old
version forever and nothing reports it.

**CI from a clean clone.** Works with no configuration and no credentials.
This is the registry's main advantage.

**Build step.** Effectively forced. Lit's publishing guidance is to ship
unbundled ES2021 modules with `.d.ts` and `.d.ts.map`, `types` set, and `lit`
as a regular dependency rather than a devDependency
(<https://lit.dev/docs/tools/publishing/>). Publishing raw `.ts` is not
forbidden by npm, but Node will not execute it from `node_modules` and bundlers
exclude `node_modules` from transpilation by default, so every consumer needs
an explicit rule.

**Cost.** Free for public packages (<https://docs.npmjs.com/about-npm>).
Publishing requires 2FA or a granular token with bypass enabled
(<https://docs.npmjs.com/about-two-factor-authentication>); trusted publishing
over OIDC from GitHub Actions removes the long-lived token altogether
(<https://docs.npmjs.com/trusted-publishers>). Pass `--access public`
explicitly for a scoped package: docs.npmjs.com says scoped packages default to
private, while the npm CLI's own config definition says `'public'` for new
packages, and the flag makes the disagreement moot.

**Licence boundary.** `license` is a metadata string and nothing more
(<https://docs.npmjs.com/cli/v11/configuring-npm/package-json>). npm performs no
licence check anywhere in the publish or install path; its Open-Source Terms
describe only a takedown power
(<https://docs.npmjs.com/policies/open-source-terms>). `LICENSE` is always
included in the tarball, so the licence text travels with the code — exactly as
it does over a git dependency, a submodule or a copy. **The transport does not
change the licence.** What a registry does change is that the shared source
never enters either consumer's repository.

**Does it need a new repository?** No, strictly. The package can be published
from a subdirectory of an existing repository. But publishing turns the shared
package into a released artifact with its own release ritual, which is most of
the overhead of a separate repository without the clarity.

### 2.2 GitHub Packages

Same npm protocol, same pinning, same lockfile, same build step, same absence
of licence enforcement. It differs on three things.

**Scoping is mandatory.** "GitHub Packages only supports scoped npm packages…
The namespace must be the owning personal account or organization"
(<https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-npm-registry>).
A project `.npmrc` must carry `@NAMESPACE:registry=https://npm.pkg.github.com`.

**A token is needed even for a public package.** GitHub's own wording: "You need
an access token to publish, install, and delete private, internal, and public
packages" (same page), and "In most registries, to pull a package, you must
authenticate with a personal access token or `GITHUB_TOKEN`, regardless of
whether the package is public or private. However, in the Container registry,
public packages allow anonymous access"
(<https://docs.github.com/en/packages/learn-github-packages/about-permissions-for-github-packages>).
The npm registry is not in that exception list. GitHub never states it as an
npm-specific sentence, so this rests on the Container registry being the only
documented exception; **treat it as the documented position with one degree of
inference.** Only classic personal access tokens are supported — fine-grained
PATs are not (same page).

**Cross-repository access in Actions needs a grant.** `GITHUB_TOKEN`'s
"permissions are limited to the repository that contains your workflow"
(<https://docs.github.com/en/actions/concepts/security/github_token>). To let
the second repository's workflow install the package, the package's settings
page has **Manage Actions access → Add Repository**: "you must give GitHub
Actions access to the repositories where your workflow is run"
(<https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility>).
Without it, the second repository needs a classic PAT as a secret.

**First publish is private by default** and must be changed explicitly (same
page). A private package draws on the plan quota shared with Actions artifacts;
public packages are free
(<https://docs.github.com/en/billing/concepts/product-billing/github-packages>).

**Failure mode.** Every clean clone — a laptop without a PAT, a Netlify or
Vercel build, a Docker build, Dependabot — fails with a `404` from
`npm.pkg.github.com`, and a `404` looks identical whether the cause is a
missing version or a missing token. For an open-source-shaped project this is
the dominant cost and it buys nothing over the public registry.

npm provenance on GitHub Packages is **undocumented**: GitHub's own workflow
example uses `--provenance` only for npmjs.com and omits it from the GitHub
Packages example
(<https://docs.github.com/en/actions/publishing-packages/publishing-nodejs-packages>),
and no page states either support or exclusion.

### 2.3 Git dependency

Covered in §1 for the subdirectory case. For a whole-repository dependency both
npm and pnpm work.

**Pinning.** `#<commit-ish>` clones exactly that commit; `#semver:<range>`
matches tags or refs in the remote
(<https://docs.npmjs.com/cli/v11/configuring-npm/package-json>). Both lockfiles
record the resolved commit SHA, so a clean clone is reproducible even if the
branch moves.

**Cost of a change.** Push to the shared repository, then in each consumer
re-resolve (`pnpm update <pkg>`) and commit the lockfile. No publish, no
version bump, no registry account. This is the cheapest release ritual of any
mechanism that keeps the source out of the consumer's tree.

**Drift.** A consumer pinned to a commit stays there silently. A consumer
pinned to a branch moves whenever the lockfile is re-resolved, which is
invisible in a PR diff apart from the lockfile line.

**CI from a clean clone.** Works if the shared repository is public. If it is
private, the runner needs credentials for it, and the default `GITHUB_TOKEN`
does not reach another repository (same citation as §2.2).

**Build step.** Forced if the package has a `prepare` script, and then pnpm 11
requires an `allowBuilds` entry (§1). Not forced otherwise: a package with
`exports` pointing at `src/index.ts` and no build installs as-is. That makes
the git dependency the only registry-free mechanism that can carry the
`occupancy/lib` source-only convention across repositories unchanged.

**Licence boundary.** The shared source never enters the consumer's tree or
history. The consumer records a URL and a commit SHA in `package.json` and the
lockfile. This is the same structural property a registry gives, without the
registry.

**Does it need a new repository?** **No** — under pnpm. `#path:` points at a
subdirectory of a repository that already exists. This is the direct answer to
the issue's central question.

### 2.4 Git submodule

**Pinning.** A submodule "is a repository embedded inside another repository"
with "its own history"
(<https://git-scm.com/docs/gitsubmodules>). The pin is a `160000` gitlink entry
in the superproject's tree, which "contains the object name of the commit that
the superproject expects the submodule's working directory to be at" (same
page). `.gitmodules` records only `path` and `url`, plus optional `branch`,
`update`, `ignore`, `shallow` — **no commit and no subdirectory key**
(<https://git-scm.com/docs/gitmodules>).

**Cost of a change.** One commit in the consumer, whose diff is one line
(`-Subproject commit <old>` / `+Subproject commit <new>`):

```
git -C ui fetch origin && git -C ui checkout <sha> && git add ui && git commit
```

`git submodule update --remote` changes which SHA is targeted but does not
commit for you (<https://git-scm.com/docs/git-submodule>).

**Drift.** A force-push or GC in the shared repository breaks *every*
superproject commit that names the vanished object, not just the tip: `git
submodule update` dies with `Fetched in submodule path '%s', but it did not
contain %s`. A contributor who clones without `--recurse-submodules` gets an
empty directory — the documented "deinitialized submodule" state, "Gitlink and
`.gitmodules` entry exist, but no working directory"
(<https://git-scm.com/docs/gitsubmodules>).

**CI from a clean clone.** `actions/checkout` has `submodules: false` by
default. With `submodules: true` it works for a **public** submodule repository
with no credentials. For a private one it does not: the README says
"`${{ github.token }}` is scoped to the current repository, so if you want to
checkout a different repository that is private you will need to provide your
own PAT" (<https://github.com/actions/checkout>). The checkout action
propagates its token into submodules only when `persist-credentials` is true.

**Build step.** None at the git level. The submodule directory is an ordinary
directory in the consumer's tree and can be a pnpm workspace package. The only
ordering constraint is that checkout must happen before `pnpm install`.

**Licence boundary.** The cleanest of all the mechanisms. The shared files live
in their own repository with their own root `LICENSE`, and the consumer's tree
holds a gitlink — an object name, not the files. GitHub's licence detection
reads a `LICENSE` file in the repository root
(<https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository>),
so each repository reports its own.

**Does it need a new repository? Yes, unavoidably.** `git submodule add` takes a
repository URL and a path *in the superproject*. There is no option and no
`.gitmodules` key that selects a subdirectory of the remote. A submodule is a
whole repository by definition. This is exactly the cost the issue says it
wants to avoid.

### 2.5 Git subtree

`git subtree` is not in git-scm.com's manual index —
`https://git-scm.com/docs/git-subtree` returns 404. It lives in git's
`contrib/` tree, so the primary documentation is
<https://github.com/git/git/blob/master/contrib/subtree/git-subtree.adoc>. It
ships with Apple git 2.50.1, but availability is per-distribution.

**Pinning.** `--prefix` is the path in *your* repository. `add` "create[s] the
`<prefix>` subtree by importing its contents from the given `<local-commit>` or
`<repository>` and `<remote-ref>`". The recorded version is a set of commit
message trailers — `git-subtree-dir:`, `git-subtree-mainline:`,
`git-subtree-split:` — which the script later finds with `git log --grep`
(<https://github.com/git/git/blob/master/contrib/subtree/git-subtree.sh>).
Nothing validates them, `git status` shows no drift, and they survive only as
long as the commit message survives verbatim.

**Cost of a change.** `git subtree pull --prefix=… <repo> <ref> --squash`. One
command, but it produces a **merge commit**, and the recorded diff contains
every changed file of the shared package, permanently, in the consumer's
history.

This collides with how this repository lands work. `main` "only moves by PR
with the `ci` check green — a ruleset with no bypass" and rebase merge keeps
history linear (`CLAUDE.md`). A subtree merge commit cannot land as a merge
commit; squash- or rebase-merging the PR flattens it, and since the join point
is discovered by grepping the commit message, the `git-subtree-*` trailers are
mangled or lost. **This interaction is not documented** — GitHub's pages on
rebase and squash merges say nothing about pull requests containing merge
commits. It needs a throwaway spike before anyone commits to subtree.

**Drift.** Conflicts are ordinary merge conflicts. The documented fragility is
in round-tripping: "Whenever you split, you need to use the same `<annotation>`,
or else you don't have a guarantee that the new re-created history will be
identical to the old one. That will prevent merging from working correctly"
(git-subtree.adoc). `--rejoin` makes `git log` show "an extra copy of every new
commit that was created".

**CI from a clean clone.** Works with no configuration and no credentials. The
files are plain tracked files. This is subtree's single largest advantage over
submodules.

**Build step.** None.

**Licence boundary.** The worst of the mechanisms. Subtree vendors the files
into the consumer's tree and its history. The MIT repository would contain
AGPL-3.0 source from the import commit onward, and removing it later does not
remove it from history.

**Does it need a new repository? No**, and this is worth recording. `git subtree
add` takes a *ref* whose root becomes `<prefix>`; there is no way to select a
subdirectory of the remote. But `split` manufactures the ref you need from a
repository that already exists:

> Extract a new, synthetic project history from the history of the `<prefix>`
> subtree of `<local-commit>` … each of those commits now has the contents of
> `<prefix>` at the root of the project instead of in a subdirectory.
>
> — git-subtree.adoc

`git subtree split --prefix=src/ui -b ui-dist` puts that synthetic history on a
branch of the same repository, which the consumer then adds and pulls from.
Repeated splits are stable: "Repeated splits of exactly the same history are
guaranteed to be identical … as long as the settings passed to `split` … are
the same."

### 2.6 Consuming as source across repositories

This is the `occupancy/lib` convention applied across a repository boundary.
Inside `occupancy` it works today: six packages listed in `pnpm-workspace.yaml`
under `lib/*`, each with `exports` pointing straight at `./src/index.ts`, none
built and none published (`occupancy/lib/CLAUDE.md`).

Across repositories the mechanism is either the `link:` protocol or a workspace
glob that escapes the root. Both are covered in §2.7, because they turn out to
be the same thing with the same failure mode.

The parts specific to source consumption:

**Pinning.** There is none. The consumer gets whatever is checked out in the
sibling directory at that moment. Neither lockfile records a version, a commit
or a content hash *(tested)* — the `pnpm-lock.yaml` entry is literally
`version: link:../shared`.

**Cost of a change.** Zero. Edit the file, the consumer sees it. This is the
mechanism's entire appeal and it is a genuine one during development.

**Drift.** Not detectable. The two repositories can disagree about the shared
package indefinitely with nothing to report it, because there is no version to
compare.

**Build step.** None, which is the point. It is also the only mechanism where
the consumer type-checks the shared package's actual source rather than its
`.d.ts`, so a type error in the shared package surfaces in the consumer's
`tsc --noEmit`.

**Licence boundary.** The files stay in their own repository. Nothing is
vendored. But the consumer's build output *contains* the shared code, which is
the same position a registry dependency puts it in.

**Does it need a new repository?** No.

### 2.7 pnpm workspaces spanning more than one checkout

**It works, and it is worse than it looks.**

*(tested)* A `pnpm-workspace.yaml` whose `packages` glob escapes the workspace
root is accepted:

```yaml
packages:
  - '.'
  - '../shared'
```

```
$ pnpm install
Scope: all 2 workspace projects
+ @x/shared 1.0.0 <- ../shared
```

`node_modules/@x/shared` becomes a symlink to `../../../shared`. The `link:`
protocol reaches the same result without any workspace file at all: a
dependency of `"@x/shared": "link:../shared"` installs cleanly and records
`version: link:../shared` in the lockfile *(tested)*. pnpm also documents
`"foo": "workspace:../foo"` (<https://pnpm.io/workspaces>).

The failure mode is the reason this is a local-development mechanism only.
*(tested)* With the sibling directory removed, simulating a clean CI clone that
has only one of the two repositories:

```
$ rm -rf node_modules && pnpm install --frozen-lockfile
Lockfile is up to date, resolution step is skipped
+ @x/shared 0.0.0 <- ../shared
Done in 162ms
```

**The install succeeds.** It reports version `0.0.0` and leaves a dangling
symlink. Nothing fails until something imports the package:

```
Error: Cannot find module '@x/shared'
```

So CI goes green on install and red much later, in the build or the test run,
with an error that names a missing module rather than a missing checkout. That
is a worse signal than a failed install would be. `--frozen-lockfile` does not
help, because the lockfile faithfully records a relative path and the path is
what is missing.

It can be made to work in CI by checking out both repositories into the right
relative positions — `actions/checkout` with a `path:` input, and a PAT if the
other repository is private. At that point the arrangement is a two-repository
checkout held together by a relative path that no tool validates, which is a
lot of machinery to avoid pinning a version.

**Summary:** real for local development, and genuinely good there. Not a
sharing mechanism in its own right. It pairs well with any of the others: pin a
git or registry dependency for CI, and use a `link:` override locally when
working on both at once.

### 2.8 Copy with a divergence check

No primary documentation exists — this is a design you write, so nothing in
this section is sourced.

**Pinning.** Only what you choose to record. A source commit SHA in a
`SOURCE.txt` or in the copied `package.json` is the equivalent of a gitlink,
but nothing enforces it.

**Cost of a change.** Copy the files, commit. One commit, no merge commit, so
it lands cleanly under the rebase-merge rule that subtree violates.

**Drift.** The check goes red and blocks unrelated work. On this repository
that matters more than usual, because `main` moves only by PR with `ci` green
and no bypass. A drift check *inside* `ci` means any upstream change red-lights
every open PR in the consumer until someone syncs.

Two mitigations, both free: run the check as a separate non-required workflow
or a scheduled job that opens a sync PR; and compare against the **recorded
SHA**, not the source's tip, so the check only fails on a genuine local edit of
copied files. The second is strictly better and needs no network.

**CI from a clean clone.** Works, no credentials, provided the check compares
against a recorded hash rather than fetching the source.

**Build step.** None.

**Licence boundary.** Same as subtree: the files are in the consumer's tree and
history. Copying AGPL-3.0 source into the MIT repository puts it there
permanently.

**Does it need a new repository?** No. It is the only mechanism with no
git-level coupling at all. It is also what `control` already does — it copied
`occupancy`'s chrome by hand and says so in comments — minus the check.

---

## 3. Summary table

| | New repo? | Source in consumer's tree? | Version pinned? | CI from clean clone | Build step |
|---|---|---|---|---|---|
| Public npm | No | No | Semver + lockfile | Works, no credentials | Yes, by convention |
| GitHub Packages | No | No | Semver + lockfile | Needs a token even when public | Yes, by convention |
| Git dep, whole repo | Yes¹ | No | Commit SHA in lockfile | Works if the repo is public | Only if `prepare` exists |
| Git dep, `#path:` | **No** | No | Commit SHA in lockfile | Works if the repo is public | Only if `prepare` exists |
| Submodule | **Yes** | No — a gitlink | Gitlink commit | Works if the repo is public | No |
| Subtree | No² | **Yes, permanently** | Commit-message trailers | Works, no credentials | No |
| Source across repos | No | No | **None** | Install passes, build fails | No |
| pnpm workspace across checkouts | No | No | **None** | Install passes, build fails | No |
| Copy + check | No | **Yes, permanently** | Only what you record | Works, no credentials | No |

¹ A whole-repository git dependency needs the shared package at the repository
root, so it needs its own repository. `#path:` is what removes that.

² Subtree needs no new repository, but only via `git subtree split -b <branch>`
pushed to a branch of an existing one. `git subtree add` itself always takes a
ref whose root is the package.

---

## 4. Two things that cut across every mechanism

### 4.1 The duplication that actually breaks a Lit UI

The common worry is two copies of Lit. That is not the one that bites. Lit's
own documentation says duplicated Lit is a dev-mode warning and wasted bytes:

> If Lit is being used as an internal dependency of elements, elements can use
> different versions of Lit and are completely interoperable. … Loading
> multiple compatible versions of Lit is non-optimal because extra duplicated
> bytes must be sent to the user.
>
> — <https://lit.dev/docs/tools/development/#multiple-versions-of-lit-warning>

The fatal duplication is of **the shared component package itself**, because
custom element registration is global by tag name and a second registration is
a hard error:

> If *this*'s custom element definition set contains an item with name *name*,
> then throw a `"NotSupportedError"` `DOMException`.
>
> — <https://html.spec.whatwg.org/multipage/custom-elements.html#custom-elements-api>

This only matters if both apps are ever composed into one document. Today they
are separate pages, so it does not. If that changes, the shared package must
resolve to exactly one version in that document — an exact pin rather than a
caret range, or a root `overrides` entry in both consumers. Note that pnpm 11
moved `overrides` out of `package.json` into `pnpm-workspace.yaml`
(<https://pnpm.io/settings/dependency-resolution>), so anything written for
pnpm 10 will silently do nothing.

Lit's related publishing rule, if a registry is ever chosen: do not bundle
before publishing, because "npm can't deduplicate the packages"
(<https://lit.dev/docs/tools/publishing/>).

### 4.2 The licence boundary

No mechanism enforces anything. npm has no licence check in the publish or
install path; GitHub Packages has no licence field at all; git has no opinion.
The `license` field and the `LICENSE` file are metadata that travel with the
code whichever way it moves.

What the mechanisms do differ on is one structural fact, and it is the only one
worth deciding on:

- **Registry, git dependency, submodule, source-across-repos**: the shared
  source never enters the consumer's repository or its history. The consumer
  records a name, a URL or an object name.
- **Subtree, copy**: the shared source is committed into the consumer's tree
  and stays in its history forever. Removing it later does not remove it.

Whether AGPL-3.0 source in an MIT repository's history is acceptable is a
licence question, not a packaging question, and this document does not answer
it. The packaging question it does answer is that four of the mechanisms make
the question moot and two of them force it.

A secondary point: GitHub reports a repository's licence from a `LICENSE` file
in the repository root
(<https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository>).
A `LICENSE` inside a vendored subdirectory is not what GitHub shows for that
repository.

---

## 5. Where the documentation is unclear or version-dependent

Stated plainly rather than guessed at.

1. **Anonymous pulls of a public npm package from GitHub Packages.** GitHub says
   "in most registries … regardless of whether the package is public or
   private", and names only the Container registry as the exception. No
   npm-specific sentence exists either way.
2. **npm provenance on GitHub Packages.** No support statement, no exclusion
   statement.
3. **`--access` default for scoped npm packages.** docs.npmjs.com says private;
   the npm CLI's config definition says `'public'` for new packages. Pass the
   flag.
4. **`link:` and `file:` as pnpm `overrides` values.** Not documented either
   way.
5. **A pull request containing a subtree merge commit under a rebase-merge
   rule.** GitHub's merge documentation does not address it. Needs a spike.
6. **pnpm version dependence.** `pnpm.overrides` in `package.json` stopped
   being read in v11; `pnpm link`'s bare and `--global` forms were removed in
   v11; `#path:` on git dependencies requires v9 or later. `git subtree` is in
   git's `contrib/` and its availability is per-distribution.

---

## 6. What this leaves

Nothing here is a decision. Three observations that the issue's constraints
select for:

The "no new repository" constraint rules out submodules outright and leaves
everything else. Of what remains, **a pnpm git dependency with `#path:`** is
the only one that keeps the source out of both consumers' histories, pins an
exact commit in the lockfile, needs no registry account and no token for a
public repository, and — if the shared package keeps the `occupancy/lib`
source-only convention with no `prepare` script — forces no build step. Its
costs are that it makes pnpm mandatory, that `#semver:` is unsafe in a
multi-package repository, and that the whole repository is transferred on every
fetch.

The public npm registry is the option with the fewest unknowns and the most
friction per change. GitHub Packages is the same thing with a token problem and
no compensating advantage for a public project.

A cross-checkout pnpm workspace or `link:` is a good local-development pairing
for any of the above, and a poor sharing mechanism on its own, because a
missing sibling checkout passes `pnpm install --frozen-lockfile` and fails much
later.
