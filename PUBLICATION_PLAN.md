# BirOvoz — gradual publication

This delivery groups the completed work into three commits: backend reliability,
interface workflows, and local startup/documentation. Earlier local commits are
retained separately as a checkpoint. The patches also allow independent review.

Base master: `637d6afcbe83479ade012aacbcf9a29c28647bad`.
These patches target that baseline, not the already imported local completion
branch. If your checkout differs, run `git apply --check` before applying. Do not
apply both the previous completion bundle and these patches to the same branch.
Existing local files and secrets must be preserved; use a clean working tree.

## Block 1 — backend reliability and session lifecycle

`01-backend.patch`: WAV validation, ffmpeg deadline, empty speech, current daemon
regressions, relative wrapper paths, runtime readiness, FastAPI lifespan,
bounded/thread-safe session history and automated test discovery/CI.

```bash
git apply --check /path/to/01-backend.patch
git apply /path/to/01-backend.patch
```

Review the applied diff, stage the files listed by `git apply --stat`, and create
one commit: `Harden audio processing and bound session lifecycle`.

## Block 2 — complete local demo experience

`02-interface.patch`: stream errors and cancellation/recovery, Stop/New session,
English recording upload, audio download, benchmark races/cancellation/export,
mock/live readiness and focused frontend/endpoint regressions.

Apply and review as above after Block 1. Suggested commit:
`Complete dubbing controls and benchmark result workflow`.

## Block 3 — startup and acceptance

`03-startup-docs.patch`: offline preflight/launcher, current setup instructions,
MVP scope, pending Windows/GPU/live-provider acceptance and this publication plan.

Apply after Blocks 1–2. Suggested commit:
`Add local startup checks and MVP acceptance guide`.

Commit each block when you actually review it; no specific calendar dates are
required. You may publish one block per day or at another pace. Pushing existing
commits on a later day does not change their original commit dates.

## Verification

Complete updated suite in this environment: **258 passed** (Linux/Python 3.12,
provider/model substitutes). Prior checkpoint also passed real ffmpeg + MOCK API
end-to-end checks. Real browser, live-provider and Windows/GPU acceptance remains
pending in `MVP_ACCEPTANCE.md`. Publication was authorized by the user. No PR or history rewrite is required.
