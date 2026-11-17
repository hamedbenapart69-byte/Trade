#include "cfss/l1_contract.hpp"
#include "cfss/hash.hpp"
#include "cfss/atomic_file.hpp"
#include "cfss/okx_provider.hpp"

#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>

namespace {
std::int64_t now_epoch_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}
void write_json(const std::filesystem::path& path, const nlohmann::json& value) {
    cfss::write_file_atomic(path, value.dump(2) + "\n", true);
}
int run_collect(int symbols, int years, const std::filesystem::path& l1_path,
                const std::filesystem::path& l2_path) {
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK)
        throw std::runtime_error("curl_global_init_failed");
    try {
        const auto contract = cfss::okx::collect(symbols, years);
        write_json(l1_path, contract);
        const auto evidence_dir = l1_path.parent_path().empty() ? std::filesystem::path{"."} : l1_path.parent_path();
        write_json(evidence_dir / "provider-health.v1.json", contract.at("provider_health"));
        write_json(evidence_dir / "fear-greed.v1.json", contract.at("fear_greed"));
        auto artifact = cfss::build_l2_artifact(contract, now_epoch_ms());
        cfss::add_artifact_hash(artifact);
        write_json(l2_path, artifact);
        std::cout << "CPP_L1_COLLECTED provider=okx symbols=" << contract.at("instruments").size()
                  << " run_id=" << contract.at("run_id") << '\n';
        std::cout << "L2_ARTIFACT_CREATED instruments=" << artifact.at("instruments").size() << '\n';
        curl_global_cleanup();
        return EXIT_SUCCESS;
    } catch (...) {
        curl_global_cleanup();
        throw;
    }
}
}
int main(int argc, char** argv) {
    try {
        if (argc == 6 && std::string{argv[1]} == "--collect-okx") {
            return run_collect(std::stoi(argv[2]), std::stoi(argv[3]), argv[4], argv[5]);
        }
        if (argc != 3) {
            std::cerr << "Usage: market_pipeline <l1-contract.json> <l2-artifact.json>\n"
                      << "   or: market_pipeline --collect-okx <symbols:1..100> <years:1..2> <l1.json> <l2.json>\n";
            return EXIT_FAILURE;
        }
        const std::filesystem::path input_path{argv[1]};
        const std::filesystem::path output_path{argv[2]};
        std::ifstream input(input_path, std::ios::binary);
        if (!input) throw std::runtime_error("l1_contract_open_failed");
        const std::string raw{std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
        const auto contract = nlohmann::json::parse(raw);
        auto artifact = cfss::build_l2_artifact(contract, now_epoch_ms());
        cfss::add_artifact_hash(artifact);
        write_json(output_path, artifact);
        std::cout << "L2_ARTIFACT_CREATED run_id=" << contract.at("run_id")
                  << " instruments=" << artifact.at("instruments").size() << '\n';
        return EXIT_SUCCESS;
    } catch (const std::exception& error) {
        std::cerr << "PIPELINE_REJECTED: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
