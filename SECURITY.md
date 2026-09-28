# Security

This alpha supports local/CI observation and trusted-network collector forwarding.
The watcher has no authentication or TLS and is not a durable tracing backend.
Keep its default loopback bind; secure any remote deployment outside this process.

Requests and decompressed payloads are capped at 1 MiB; session deduplication is
capped at 100,000 spans by default. These bounds do not make the Python HTTP server
suitable for hostile public traffic. Exceeding capacity makes the session incomplete.

Checks execute ordinary Python in the application process. They must be trusted,
pure, fast, synchronous code. A check can mutate an object or block indefinitely;
Melampus cannot prevent that. The execution budget limits count, not runtime.

Hashes are not anonymization. Function paths, check IDs and generator labels are
visible. Avoid sensitive identifiers. SDK checks never capture application values
or exception text, but other OTel instrumentation may do so.

For a suspected vulnerability, use GitHub's private vulnerability reporting if
enabled for this repository. Otherwise contact the maintainers privately through
their GitHub profiles before sharing details; do not put exploit details or secrets
in a public issue. Only the latest alpha is maintained until a stable policy exists.
