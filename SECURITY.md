# Security

## Report privately

Use [GitHub private vulnerability reporting](https://github.com/jamespeirano/JARVISS/security/advisories/new). The maintainer is [@jamespeirano](https://github.com/jamespeirano).

Include the affected version, a short description, impact and reproduction steps using synthetic data. Do not include real conversations, locations, passwords, signing material or private documents. Do not post an exploitable vulnerability in a public issue.

Security fixes target the latest release. A response time is not guaranteed.

## Signing boundary

Apple and Windows signing credentials are held outside this repository. GitHub Actions builds and pull requests receive no signing credentials or signing role. Only a maintainer can sign and publish an official release.

Downloaded installers contain public verification certificates. Those certificates do not include private signing keys and do not let someone sign another program.

## Local data

Saved records are plaintext. The optional local message board uses local HTTP, a shared access code, and no internet relay. Do not expose it to the public internet. Include synthetic examples when reporting a problem.
