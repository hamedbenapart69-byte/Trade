#pragma once
#include <nlohmann/json.hpp>
#include <openssl/sha.h>
#include <iomanip>
#include <sstream>
#include <string>

namespace cfss {
inline std::string sha256_hex(const std::string& input) {
    unsigned char digest[SHA256_DIGEST_LENGTH]{};
    SHA256(reinterpret_cast<const unsigned char*>(input.data()), input.size(), digest);
    std::ostringstream output;
    output << std::hex << std::setfill('0');
    for (const auto byte : digest) output << std::setw(2) << static_cast<unsigned int>(byte);
    return output.str();
}
inline void add_artifact_hash(nlohmann::json& artifact) {
    artifact.erase("artifact_sha256");
    const std::string canonical = artifact.dump(-1, ' ', false, nlohmann::json::error_handler_t::strict);
    artifact["artifact_sha256"] = sha256_hex(canonical);
}
inline bool verify_artifact_hash(const nlohmann::json& artifact) {
    if (!artifact.is_object() || !artifact.contains("artifact_sha256") ||
        !artifact.at("artifact_sha256").is_string()) return false;
    const std::string expected = artifact.at("artifact_sha256").get<std::string>();
    auto canonical_artifact = artifact;
    canonical_artifact.erase("artifact_sha256");
    const std::string canonical = canonical_artifact.dump(-1, ' ', false, nlohmann::json::error_handler_t::strict);
    return expected == sha256_hex(canonical);
}
} // namespace cfss
