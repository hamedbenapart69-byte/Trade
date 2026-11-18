#pragma once

#include <array>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

namespace cfss::nss {

enum class DataClass { REAL, PROXY, UNAVAILABLE };

struct Component {
    std::string id;
    std::optional<double> score;
    DataClass data_class{DataClass::UNAVAILABLE};
    std::int64_t available_at_ms{};
    std::string definition_id;
};

struct Result {
    std::string version{"NSS_V1_FORMULA"};
    std::string status{"UNAVAILABLE"};
    std::optional<double> score;
    std::array<std::string, 5> missing{};
    std::size_t missing_count{};
};

inline constexpr std::array<std::string_view, 5> component_ids{
    "NSS1_OPEN_INTEREST_GROWTH",
    "NSS2_HEALTHY_FUNDING",
    "NSS3_BASIS_EXPANSION",
    "NSS4_VOLUME_EXPANSION",
    "NSS5_PRE_BREAKOUT_COMPRESSION"
};
inline constexpr std::array<double, 5> weights{0.30, 0.20, 0.20, 0.15, 0.15};

// تجمیع سخت‌گیرانه: فقط امتیازهای REAL و هم‌زمان‌معتبر پذیرفته می‌شوند.
inline Result aggregate_v1(const std::array<Component, 5>& components,
                           std::int64_t decision_time_ms) {
    Result result{};
    double weighted_sum = 0.0;
    for (std::size_t i = 0U; i < components.size(); ++i) {
        const auto& component = components[i];
        const bool valid =
            component.id == component_ids[i] &&
            component.definition_id.size() > 0U &&
            component.score.has_value() &&
            std::isfinite(*component.score) &&
            *component.score >= 0.0 && *component.score <= 1.0 &&
            component.available_at_ms > 0 &&
            component.available_at_ms <= decision_time_ms &&
            component.data_class == DataClass::REAL;
        if (!valid) {
            result.missing[result.missing_count++] = std::string(component_ids[i]);
            continue;
        }
        weighted_sum += weights[i] * *component.score;
    }
    // وزن مؤلفهٔ مفقود بازتوزیع نمی‌شود و مقدار صفر جایگزین آن نیست.
    if (result.missing_count != 0U) return result;
    result.score = weighted_sum;
    result.status = "CALCULATED";
    return result;
}

} // namespace cfss::nss
