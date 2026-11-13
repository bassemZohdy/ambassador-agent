"""Protocol bindings: how the core system reaches an ambassador over the wire.

A binding maps `Ambassador.describe()` to the protocol's discovery document and maps
protocol messages to `Ambassador.perform()`. A2A is the reference; the same two mappings
are all an MCP, gRPC or message-queue binding needs.
"""
