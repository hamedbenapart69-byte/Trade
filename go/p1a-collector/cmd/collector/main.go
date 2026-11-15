package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"time"

	"trade-p1a-collector/internal/collector"
)

func main() {
	var req collector.Request
	if err := json.NewDecoder(os.Stdin).Decode(&req); err != nil {
		fmt.Fprintln(os.Stderr, "invalid_input:", err)
		os.Exit(2)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	result, err := collector.New(collector.Config{Workers: 8}).Collect(ctx, req)
	if err != nil {
		fmt.Fprintln(os.Stderr, "collection_failed:", err)
		os.Exit(1)
	}
	enc := json.NewEncoder(os.Stdout)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(result); err != nil {
		fmt.Fprintln(os.Stderr, "output_failed:", err)
		os.Exit(1)
	}
}
