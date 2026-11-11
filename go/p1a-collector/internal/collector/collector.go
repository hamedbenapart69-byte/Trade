package collector

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/url"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

type Candle struct {
	Timestamp int64   `json:"timestamp"`
	Open      float64 `json:"open"`
	High      float64 `json:"high"`
	Low       float64 `json:"low"`
	Close     float64 `json:"close"`
	Volume    float64 `json:"volume"`
}

type SymbolResult struct {
	Symbol   string   `json:"symbol"`
	Timeframe string  `json:"timeframe"`
	DataClassification string `json:"data_classification"`
	VolumeUnit string `json:"volume_unit"`
	Provider string   `json:"provider"`
	Status   string   `json:"status"`
	Candles  []Candle `json:"candles"`
	Errors   []string `json:"errors"`
}

type Request struct {
	Symbols   []string `json:"symbols"`
	Timeframe string   `json:"timeframe"`
	Limit     int      `json:"limit"`
	AsOfMS    int64    `json:"as_of_ms,omitempty"`
}

type Response struct {
	SchemaVersion string         `json:"schema_version"`
	Timeframe     string         `json:"timeframe"`
	GeneratedAt   string         `json:"generated_at_utc"`
	CollectionElapsedMS int64 `json:"collection_elapsed_ms"`
	Results       []SymbolResult `json:"results"`
}

type Config struct {
	OKXBaseURL   string
	BybitBaseURL string
	HTTPClient   *http.Client
	Workers      int
	Now          func() time.Time
}

type Collector struct {
	cfg Config
}

func New(cfg Config) *Collector {
	if cfg.OKXBaseURL == "" { cfg.OKXBaseURL = "https://www.okx.com" }
	if cfg.BybitBaseURL == "" { cfg.BybitBaseURL = "https://api.bybit.com" }
	if cfg.HTTPClient == nil { cfg.HTTPClient = &http.Client{Timeout: 15 * time.Second} }
	if cfg.Workers <= 0 { cfg.Workers = 8 }
	if cfg.Now == nil { cfg.Now = time.Now }
	return &Collector{cfg: cfg}
}

func (c *Collector) Collect(ctx context.Context, req Request) (Response, error) {
	if len(req.Symbols) == 0 { return Response{}, errors.New("symbols_required") }
	if req.Timeframe == "" { req.Timeframe = "15m" }
	if req.Timeframe != "15m" { return Response{}, errors.New("unsupported_timeframe") }
	if req.Limit <= 0 { req.Limit = 100 }
	if req.Limit > 300 { return Response{}, errors.New("limit_exceeds_okx_max_300") }

	symbols := make([]string, 0, len(req.Symbols))
	seen := map[string]bool{}
	for _, raw := range req.Symbols {
		s := strings.ToUpper(strings.TrimSpace(raw))
		if s == "" || !strings.HasSuffix(s, "USDT") || len(s) <= 4 {
			return Response{}, fmt.Errorf("invalid_usdt_perpetual_symbol:%q", raw)
		}
		if seen[s] { return Response{}, fmt.Errorf("duplicate_symbol:%s", s) }
		seen[s] = true
		symbols = append(symbols, s)
	}
	sort.Strings(symbols)

	started := time.Now()
	scanNow := c.cfg.Now().UTC()
	if req.AsOfMS > 0 { scanNow = time.UnixMilli(req.AsOfMS).UTC() }
	type job struct{ index int; symbol string }
	jobs := make(chan job)
	results := make([]SymbolResult, len(symbols))
	var wg sync.WaitGroup
	workers := c.cfg.Workers
	if workers > len(symbols) { workers = len(symbols) }
	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := range jobs {
				results[j.index] = c.collectOne(ctx, j.symbol, req.Limit, scanNow)
			}
		}()
	}
	for i, s := range symbols {
		select {
		case jobs <- job{index:i, symbol:s}:
		case <-ctx.Done():
			close(jobs); wg.Wait(); return Response{}, ctx.Err()
		}
	}
	close(jobs)
	wg.Wait()
	return Response{SchemaVersion:"1.0.0", Timeframe:"15m", GeneratedAt:scanNow.Format(time.RFC3339Nano), CollectionElapsedMS:time.Since(started).Milliseconds(), Results:results}, nil
}

func (c *Collector) collectOne(ctx context.Context, symbol string, limit int, scanNow time.Time) SymbolResult {
	out := SymbolResult{Symbol:symbol, Timeframe:"15m", DataClassification:"UNAVAILABLE", VolumeUnit:"UNAVAILABLE", Status:"UNAVAILABLE", Candles:[]Candle{}, Errors:[]string{}}
	for _, provider := range []string{"okx", "bybit"} {
		if ctx.Err() != nil { out.Errors = append(out.Errors, "context:"+ctx.Err().Error()); return out }
		var candles []Candle
		var err error
		if provider == "okx" { candles, err = c.fetchOKX(ctx, symbol, limit, scanNow) } else { candles, err = c.fetchBybit(ctx, symbol, limit, scanNow) }
		if err != nil {
			out.Errors = append(out.Errors, provider+":"+err.Error())
			continue
		}
		if len(candles) == 0 {
			out.Errors = append(out.Errors, provider+":no_closed_candles")
			continue
		}
		volumeUnit := "BASE_ASSET"
		out.Provider, out.Status, out.DataClassification, out.VolumeUnit, out.Candles = provider, "OK", "REAL", volumeUnit, candles
		return out // Never mix candles from different venues for one symbol.
	}
	return out
}

func (c *Collector) getJSON(ctx context.Context, endpoint string, query url.Values, target any) error {
	u, err := url.Parse(endpoint); if err != nil { return err }
	u.RawQuery = query.Encode()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil); if err != nil { return err }
	req.Header.Set("Accept", "application/json")
	resp, err := c.cfg.HTTPClient.Do(req); if err != nil { return err }
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 4<<20)); if err != nil { return err }
	if resp.StatusCode == 451 { return errors.New("BLOCKED_REGION") }
	if resp.StatusCode == 429 { return errors.New("RATE_LIMITED") }
	if resp.StatusCode == 403 { return errors.New("FORBIDDEN") }
	if resp.StatusCode < 200 || resp.StatusCode >= 300 { return fmt.Errorf("http_status_%d", resp.StatusCode) }
	if err := json.Unmarshal(body, target); err != nil { return fmt.Errorf("invalid_json:%w", err) }
	return nil
}

func (c *Collector) fetchOKX(ctx context.Context, symbol string, limit int, scanNow time.Time) ([]Candle, error) {
	var payload struct {
		Code string `json:"code"`
		Msg string `json:"msg"`
		Data [][]string `json:"data"`
	}
	inst := strings.TrimSuffix(symbol, "USDT") + "-USDT-SWAP"
	q := url.Values{"instId":{inst}, "bar":{"15m"}, "limit":{strconv.Itoa(limit)}}
	if err := c.getJSON(ctx, c.cfg.OKXBaseURL+"/api/v5/market/candles", q, &payload); err != nil { return nil, err }
	if payload.Code != "" && payload.Code != "0" { return nil, fmt.Errorf("provider_code_%s:%s", payload.Code, payload.Msg) }
	rows := make([]Candle, 0, len(payload.Data))
	for _, row := range payload.Data {
		if len(row) < 9 { return nil, errors.New("MALFORMED_OKX_CANDLE_ROW") }
		if row[8] == "0" { continue }
		if row[8] != "1" { return nil, fmt.Errorf("INVALID_OKX_CONFIRM_FLAG:%s", row[8]) }
		ts, err := strconv.ParseInt(row[0],10,64)
		if err != nil { return nil, fmt.Errorf("INVALID_OKX_TIMESTAMP:%w", err) }
		vals := make([]float64,5)
		for i:=0; i<4; i++ {
			value, parseErr := strconv.ParseFloat(row[i+1],64)
			if parseErr != nil { return nil, fmt.Errorf("INVALID_OKX_VALUE:%w", parseErr) }
			vals[i] = value
		}
		// CCXT's OKX swap OHLCV volume is volCcy (base asset), not vol (contracts).
		volume, parseErr := strconv.ParseFloat(row[6],64)
		if parseErr != nil { return nil, fmt.Errorf("INVALID_OKX_BASE_VOLUME:%w", parseErr) }
		vals[4] = volume
		rows = append(rows,Candle{Timestamp:ts,Open:vals[0],High:vals[1],Low:vals[2],Close:vals[3],Volume:vals[4]})
	}
	return normalize(rows, scanNow, limit)
}

func (c *Collector) fetchBybit(ctx context.Context, symbol string, limit int, scanNow time.Time) ([]Candle, error) {
	var payload struct {
		RetCode int `json:"retCode"`
		RetMsg string `json:"retMsg"`
		Result struct { List [][]string `json:"list"` } `json:"result"`
	}
	q := url.Values{"category":{"linear"}, "symbol":{symbol}, "interval":{"15"}, "limit":{strconv.Itoa(limit)}}
	if err := c.getJSON(ctx, c.cfg.BybitBaseURL+"/v5/market/kline", q, &payload); err != nil { return nil, err }
	if payload.RetCode != 0 { return nil, fmt.Errorf("provider_code_%d:%s",payload.RetCode,payload.RetMsg) }
	rows := make([]Candle,0,len(payload.Result.List))
	for _, row := range payload.Result.List {
		if len(row) < 6 { return nil, errors.New("MALFORMED_BYBIT_CANDLE_ROW") }
		ts, parseErr := strconv.ParseInt(row[0],10,64)
		if parseErr != nil { return nil, fmt.Errorf("INVALID_BYBIT_TIMESTAMP:%w", parseErr) }
		vals:=make([]float64,5)
		for i:=0;i<5;i++ {
			value, err := strconv.ParseFloat(row[i+1],64)
			if err != nil { return nil, fmt.Errorf("INVALID_BYBIT_VALUE:%w", err) }
			vals[i]=value
		}
		rows=append(rows,Candle{Timestamp:ts,Open:vals[0],High:vals[1],Low:vals[2],Close:vals[3],Volume:vals[4]})
	}
	return normalize(rows,scanNow,limit)
}

func normalize(rows []Candle, now time.Time, limit int) ([]Candle, error) {
	const interval int64 = 900000
	closedBefore := now.UTC().UnixMilli() / interval * interval
	unique := make(map[int64]Candle, len(rows))
	for _, row := range rows {
		if row.Timestamp < 0 || row.Timestamp%interval != 0 {
			return nil, fmt.Errorf("INVALID_CANDLE_TIMESTAMP:%d", row.Timestamp)
		}
		if _, exists := unique[row.Timestamp]; exists {
			return nil, fmt.Errorf("DUPLICATE_TIMESTAMP:%d", row.Timestamp)
		}
		values := []float64{row.Open, row.High, row.Low, row.Close, row.Volume}
		for _, value := range values {
			if math.IsNaN(value) || math.IsInf(value, 0) {
				return nil, fmt.Errorf("NON_FINITE_CANDLE_VALUE:%d", row.Timestamp)
			}
		}
		if row.Open <= 0 || row.High <= 0 || row.Low <= 0 || row.Close <= 0 || row.Volume < 0 {
			return nil, fmt.Errorf("INVALID_CANDLE_VALUE:%d", row.Timestamp)
		}
		if row.High < max(row.Open, row.Close, row.Low) || row.Low > min(row.Open, row.Close, row.High) {
			return nil, fmt.Errorf("INVALID_OHLC_RELATION:%d", row.Timestamp)
		}
		unique[row.Timestamp] = row
	}
	out := make([]Candle, 0, len(unique))
	for ts, row := range unique {
		if ts+interval <= closedBefore {
			out = append(out, row)
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Timestamp < out[j].Timestamp })
	for i := 1; i < len(out); i++ {
		delta := out[i].Timestamp - out[i-1].Timestamp
		if delta != interval {
			return nil, fmt.Errorf("DATA_GAP_OR_INTERVAL_ERROR:%d", delta)
		}
	}
	if len(out) > limit {
		out = out[len(out)-limit:]
	}
	return out, nil
}
