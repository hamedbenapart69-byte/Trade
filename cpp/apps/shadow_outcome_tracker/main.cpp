#include "cfss/shadow_outcomes.hpp"
#include "cfss/atomic_file.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

using json = nlohmann::json;

namespace {
json read_json_or_empty(const std::filesystem::path& path, const json& empty_value) {
    if (!std::filesystem::exists(path)) return empty_value;
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("shadow_input_open_failed:" + path.string());
    auto value = json::parse(input);
    if (!value.is_object()) throw std::runtime_error("shadow_input_root_invalid:" + path.string());
    return value;
}

json read_required(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("shadow_required_input_open_failed:" + path.string());
    auto value = json::parse(input);
    if (!value.is_object()) throw std::runtime_error("shadow_required_input_root_invalid");
    return value;
}

void write_json(const std::filesystem::path& path, const json& value) {
    cfss::write_file_atomic(path, value.dump(2) + "\n", true);
}
}

int main(int argc, char** argv) {
    if (argc != 9) {
        std::cerr << "usage: shadow_outcome_tracker <l1-1h.json> <l1-15m.json> <dual-engine.json> <liquidity.json> "
                     "<registry.json> <ledger.json> <registry-out.json> <ledger-out.json>\n";
        return 2;
    }
    try {
        const auto l1 = read_required(argv[1]);
        const auto l1_15m = read_required(argv[2]);
        const auto dual = read_required(argv[3]);
        const auto liquidity = read_required(argv[4]);
        const auto registry = read_json_or_empty(argv[5], cfss::shadow::empty_registry());
        const auto ledger = read_json_or_empty(argv[6], cfss::shadow::empty_ledger());
        const auto output = cfss::shadow::process(l1, l1_15m, dual, liquidity, registry, ledger);
        write_json(argv[7], output.at("registry"));
        write_json(argv[8], output.at("ledger"));
        const auto& summary = output.at("registry").at("summary");
        const auto& ledger_out = output.at("ledger");
        std::size_t proxy_costs = 0U;
        std::size_t unavailable_costs = 0U;
        for (const auto& outcome : ledger_out.at("outcomes")) {
            if (outcome.value("cost_status", std::string{"UNAVAILABLE"}) == "PROXY")
                ++proxy_costs;
            else
                ++unavailable_costs;
        }
        std::cout << "SHADOW_TRACKER_STATUS=PASS"
                  << " REGISTERED=" << summary.at("registered_this_run")
                  << " RESOLVED=" << summary.at("resolved_this_run")
                  << " PENDING=" << summary.at("pending_count")
                  << " TOTAL_OUTCOMES=" << summary.at("total_outcomes")
                  << " COST_PROXY=" << proxy_costs
                  << " COST_UNAVAILABLE=" << unavailable_costs
                  << " COST_BACKFILLED=" << ledger_out.value("cost_backfilled_this_run", 0U)
                  << " COST_MODEL=" << ledger_out.value("cost_model", json::object()).value("id", "UNAVAILABLE")
                  << "\\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "SHADOW_TRACKER_ERROR=" << error.what() << '\n';
        return 1;
    }
}
