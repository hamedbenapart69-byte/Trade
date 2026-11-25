#pragma once

#include <chrono>
#include <cstddef>
#include <mutex>
#include <string>

namespace cfss::resilience {

class CircuitBreaker {
public:
    explicit CircuitBreaker(std::size_t failure_threshold = 5U,
                            std::chrono::milliseconds cooldown = std::chrono::seconds(60))
        : failure_threshold_(failure_threshold == 0U ? 1U : failure_threshold),
          cooldown_(cooldown.count() < 0 ? std::chrono::milliseconds(0) : cooldown) {}

    bool allow_request() {
        std::lock_guard<std::mutex> lock(mutex_);
        const auto now = clock::now();
        if (open_until_ == time_point{}) return true;
        if (now < open_until_) return false;
        // The cooldown elapsed. Permit one sequential half-open probe and reset the window.
        open_until_ = time_point{};
        failures_ = 0U;
        return true;
    }

    void record_success() {
        std::lock_guard<std::mutex> lock(mutex_);
        failures_ = 0U;
        open_until_ = time_point{};
    }

    void record_failure() {
        std::lock_guard<std::mutex> lock(mutex_);
        const auto now = clock::now();
        if (open_until_ != time_point{} && now < open_until_) return;
        if (open_until_ != time_point{}) {
            open_until_ = time_point{};
            failures_ = 0U;
        }
        ++failures_;
        if (failures_ >= failure_threshold_) {
            failures_ = 0U;
            open_until_ = now + cooldown_;
        }
    }

    std::string state() const {
        std::lock_guard<std::mutex> lock(mutex_);
        if (open_until_ == time_point{}) return "CLOSED";
        return clock::now() < open_until_ ? "OPEN" : "HALF_OPEN";
    }

    void reset() {
        std::lock_guard<std::mutex> lock(mutex_);
        failures_ = 0U;
        open_until_ = time_point{};
    }

private:
    using clock = std::chrono::steady_clock;
    using time_point = clock::time_point;

    const std::size_t failure_threshold_;
    const std::chrono::milliseconds cooldown_;
    mutable std::mutex mutex_;
    std::size_t failures_{0U};
    time_point open_until_{};
};

inline CircuitBreaker& okx_circuit_breaker() {
    static CircuitBreaker breaker{5U, std::chrono::seconds(60)};
    return breaker;
}

inline CircuitBreaker& kucoin_circuit_breaker() {
    static CircuitBreaker breaker{5U, std::chrono::seconds(60)};
    return breaker;
}

} // namespace cfss::resilience
