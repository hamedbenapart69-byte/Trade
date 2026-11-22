#include "cfss/stage1_btc_contract.hpp"
#include "cfss/atomic_file.hpp"

#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>

namespace {
using json = nlohmann::json;

std::string read_text(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("stage1_input_open_failed:" + path.string());
    return {std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
}

std::int64_t now_epoch_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}
}

int main(int argc, char** argv) {
    if (argc != 4) {
        std::cerr << "Usage: stage1_btc_validate <l1-contract.json> <source-archive.zip> <l2-output.json>\n";
        return EXIT_FAILURE;
    }
    try {
        const std::string l1_raw = read_text(argv[1]);
        const std::string archive_raw = read_text(argv[2]);
        const auto contract = json::parse(l1_raw);
        const auto now_ms = now_epoch_ms();

        cfss::stage1::validate_btc_l1(contract, archive_raw, now_ms);
        const auto l2 = cfss::stage1::build_no_signal_l2(contract, now_ms);
        cfss::write_file_atomic(argv[3], l2.dump(2) + "\n", true);

        std::cout << "STAGE1_CPP_VALIDATION=PASS\n"
                  << "SYMBOL=BTCUSDT\n"
                  << "CLOSED_CANDLES=" << contract.at("instruments").at(0).at("candles").size() << '\n'
                  << "STALENESS_MS=" << contract.at("freshness").at("staleness_ms") << '\n'
                  << "SIGNAL_GENERATION=DISABLED\n"
                  << "L2_SHA256=" << l2.at("artifact_sha256") << '\n';
        return EXIT_SUCCESS;
    } catch (const std::exception& error) {
        std::cerr << "STAGE1_CPP_VALIDATION=REJECT reason=" << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
