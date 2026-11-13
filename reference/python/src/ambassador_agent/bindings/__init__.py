"""Protocol bindings: how the core system reaches an ambassador over the wire.

A binding maps `Ambassador.describe()` to the protocol's discovery document and maps
protocol messages to `Ambassador.perform()`. A2A is the reference, and MCP follows the same two mappings (one tool per capability). The same
two mappings are all a gRPC or message-queue binding needs.
"""
