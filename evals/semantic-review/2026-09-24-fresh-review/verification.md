# Verification

Run 2026-09-24T08:59:42Z from `/var/folders/qz/ycfy4hxs01321rg_7tdl5kqr0000gn/T/lg-fresh-review-v05ty19x`. No input, label or first-pass file was modified.

## 1. Input SHA256SUMS

```
$ shasum -a 256 -c SHA256SUMS
evaluator/author-labels.jsonl: OK
evaluator/author-provenance.md: OK
evaluator/author-rubric.md: OK
evaluator/evidence-id-map.json: OK
evaluator/pairs.json: OK
review-input.json: OK
exit=0
```

## 2. Preserved first-pass hash

```
$ cat first-pass.sha256
1ed5e781a8e2df64aee219cea85ebeaa935e566fd65d11d77217dbf10020de02  first-pass.md
$ shasum -a 256 -c first-pass.sha256
first-pass.md: OK
exit=0
```

## 3. Inputs unmodified since delivery

```
$ ls -l --  (mtimes)
-rw-r--r--  1 hitesh  staff  272557 24 Sep 09:46:42 2026 review-input.json
-rw-r--r--  1 hitesh  staff    3762 24 Sep 09:47:14 2026 REVIEW-INSTRUCTIONS.md
-rw-r--r--  1 hitesh  staff     554 24 Sep 09:46:42 2026 SHA256SUMS

evaluator/:
total 120
-rw-r--r--  1 hitesh  staff  15955 24 Sep 09:46:42 2026 author-labels.jsonl
-rw-r--r--  1 hitesh  staff  12892 24 Sep 09:46:42 2026 author-provenance.md
-rw-r--r--  1 hitesh  staff  17342 24 Sep 09:46:42 2026 author-rubric.md
-rw-r--r--  1 hitesh  staff   3108 24 Sep 09:46:42 2026 evidence-id-map.json
-rw-r--r--  1 hitesh  staff   2710 24 Sep 09:46:42 2026 pairs.json
```
