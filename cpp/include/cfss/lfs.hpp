#pragma once

#include <array>
#include <cmath>
#include <cstdint>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>

namespace cfss::lfs {

enum class DataClass { REAL, PROXY, UNAVAILABLE };

struct Component {
    std::string id;
    std::optional<double> score;
    DataClass data_class{DataClass::UNAVAILABLE};
    std::int64_t available_at_ms{};
    std::string definition_id;
};

struct Result {
    std::string version{"LFS_V1_FORMULA"};
    std::string status{"UNAVAILABLE"};
    std::optional<double> score;
    std::string data_class{"UNAVAILABLE"};
    std::array<std::string, 5> missing{};
    std::size_t missing_count{};
    std::size_t real_count{};
    std::size_t proxy_count{};
};

inline constexpr std::array<std::string_view, 5> component_ids{
    "LFS1_BOOK_THINNESS",
    "LFS2_FUNDING_EXTREME",
    "LFS3_LONG_SHORT_POSITIONING",
    "LFS4_VOLATILITY_COMPRESSION",
    "LFS5_OPEN_INTEREST_CHANGE"
};
inline constexpr std::array<double, 5> weights{0.25, 0.20, 0.20, 0.20, 0.15};

inline Result aggregate_v1(const std::array<Component, 5>& components,
                           std::int64_t decision_time_ms) {
    Result result{};
    double weighted_sum = 0.0;
    for (std::size_t i = 0; i < components.size(); ++i) {
        const auto& component = components[i];
        if (component.id != component_ids[i] || component.definition_id.empty() ||
            !component.score.has_value() || !std::isfinite(*component.score) ||
            *component.score < 0.0 || *component.score > 1.0 ||
            component.available_at_ms <= 0 ||
            component.available_at_ms > decision_time_ms ||
            component.data_class == DataClass::UNAVAILABLE) {
            result.missing[result.missing_count++] = std::string(component_ids[i]);
            continue;
        }
        if (component.data_class == DataClass::REAL) ++result.real_count;
        if (component.data_class == DataClass::PROXY) ++result.proxy_count;
        weighted_sum += weights[i] * *component.score;
    }

    // طبق قرارداد، وزن مؤلفهٔ گمشده بازتوزیع نمی‌شود.
    if (result.missing_count != 0U) return result;

    result.score = weighted_sum;
    result.status = "CALCULATED";
    result.data_class = result.proxy_count == 0U ? "REAL" :
                        (result.real_count == 0U ? "PROXY" : "MIXED");
    return result;
}

} // namespace cfss::lfs
