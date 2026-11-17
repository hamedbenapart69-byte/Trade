#include "cfss/l1_contract.hpp"
#include "cfss/hash.hpp"
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
}
int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "Usage: market_pipeline <l1-contract.json> <l2-artifact.json>\n";
        return EXIT_FAILURE;
    }
    try {
        const std::filesystem::path input_path{argv[1]};
        const std::filesystem::path output_path{argv[2]};
        std::ifstream input(input_path, std::ios::binary);
        if (!input) throw std::runtime_error("l1_contract_open_failed");
        const std::string raw{std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
        const auto contract = nlohmann::json::parse(raw);
        auto artifact = cfss::build_l2_artifact(contract, now_epoch_ms());
        cfss::add_artifact_hash(artifact);
        if (std::filesystem::exists(output_path))
            throw std::runtime_error("immutable_l2_artifact_already_exists");
        const auto parent = output_path.parent_path().empty() ? std::filesystem::path{"."} : output_path.parent_path();
        std::filesystem::create_directories(parent);
        const auto temp_path = output_path.string() + ".tmp";
        {
            std::ofstream output(temp_path, std::ios::binary | std::ios::trunc);
            if (!output) throw std::runtime_error("l2_artifact_temp_open_failed");
            output << artifact.dump(2) << '\n';
            output.flush();
            if (!output) throw std::runtime_error("l2_artifact_write_failed");
        }
        std::filesystem::rename(temp_path, output_path);
        std::cout << "L2_ARTIFACT_CREATED run_id=" << contract.at("run_id")
                  << " instruments=" << artifact.at("instruments").size() << '\n';
        return EXIT_SUCCESS;
    } catch (const std::exception& error) {
        std::cerr << "L2_REJECTED: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
