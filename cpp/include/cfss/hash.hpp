#pragma once
#include <nlohmann/json.hpp>
#include <openssl/evp.h>
#include <array>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>

namespace cfss {
inline std::string sha256_hex(const std::string& input) {
    std::array<unsigned char, EVP_MAX_MD_SIZE> digest{};
    unsigned int digest_length = 0;
    EVP_MD_CTX* context = EVP_MD_CTX_new();
    if (!context) throw std::runtime_error("sha256_context_allocation_failed");
    const bool ok = EVP_DigestInit_ex(context, EVP_sha256(), nullptr) == 1 &&
        EVP_DigestUpdate(context, input.data(), input.size()) == 1 &&
        EVP_DigestFinal_ex(context, digest.data(), &digest_length) == 1;
    EVP_MD_CTX_free(context);
    if (!ok || digest_length != 32U) throw std::runtime_error("sha256_digest_failed");
    std::ostringstream out;
    out << std::hex << std::setfill('0');
    for (unsigned int i = 0; i < digest_length; ++i)
        out << std::setw(2) << static_cast<unsigned int>(digest[i]);
    return out.str();
}
inline std::string artifact_hash_payload(nlohmann::json artifact) {
    artifact.erase("artifact_sha256");
    return artifact.dump();
}
inline void add_artifact_hash(nlohmann::json& artifact) {
    artifact["artifact_sha256"] = sha256_hex(artifact_hash_payload(artifact));
}
inline bool verify_artifact_hash(const nlohmann::json& artifact) {
    if (!artifact.is_object() || !artifact.contains("artifact_sha256") ||
        !artifact.at("artifact_sha256").is_string()) return false;
    return artifact.at("artifact_sha256").get<std::string>() ==
        sha256_hex(artifact_hash_payload(artifact));
}
} // namespace cfss
