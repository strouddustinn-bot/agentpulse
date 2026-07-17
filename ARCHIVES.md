# Historical Source Retention Policy

Superseded implementations and historical evidence must remain outside the active product repository.

Before deleting any source, branch, tag, patch, snapshot, or migration evidence, the owner must privately verify that:

- the retained history and uncommitted evidence are recoverable;
- integrity checks pass for every retained artifact;
- durable storage meets the owner's recovery requirements;
- the retained material has a documented source-disposition decision.

Confidential operational evidence must not be published in this repository.

The public completion gate records only the owner's pass/fail decision. A missing or failed retention confirmation blocks deletion.

Historical material must not be reintroduced into active product source without a new architecture decision and passing verification.
