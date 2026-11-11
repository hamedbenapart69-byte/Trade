package collector

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
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
	Provider string   `json:"provider"`
	Status   string   `json:"status"`
	Candles  []Candle `json:"candles"`
	Errors   []string `json:"errors"`
}

type Request struct {
	Symbols   []string `json:"symbols"`
	Timeframe string   `json:"timeframe"`
	Limit     int      `json:"limit"`
}

type Response struct {
	SchemaVersion string         `json:"schema_version"`
	GeneratedAt   string         `json:"generated_at_utc"`
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
	if req.Limit <= 0 || req.Limit > 300 { req.Limit = 100 }

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
				results[j.index] = c.collectOne(ctx, j.symbol, req.Limit)
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
	return Response{SchemaVersion:"1.0.0", GeneratedAt:c.cfg.Now().UTC().Format(time.RFC3339Nano), Results:results}, nil
}

func (c *Collector) collectOne(ctx context.Context, symbol string, limit int) SymbolResult {
	out := SymbolResult{Symbol:symbol, Status:"UNAVAILABLE", Candles:[]Candle{}, Errors:[]string{}}
	for _, provider := range []string{"okx", "bybit"} {
		var candles []Candle
		var err error
		if provider == "okx" { candles, err = c.fetchOKX(ctx, symbol, limit) } else { candles, err = c.fetchBybit(ctx, symbol, limit) }
		if err != nil {
			out.Errors = append(out.Errors, provider+":"+err.Error())
			continue
		}
		if len(candles) == 0 {
			out.Errors = append(out.Errors, provider+":no_closed_candles")
			continue
		}
		out.Provider, out.Status, out.Candles = provider, "OK", candles
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
	if resp.StatusCode < 200 || resp.StatusCode >= 300 { return fmt.Errorf("http_status_%d", resp.StatusCode) }
	if err := json.Unmarshal(body, target); err != nil { return fmt.Errorf("invalid_json:%w", err) }
	return nil
}

func (c *Collector) fetchOKX(ctx context.Context, symbol string, limit int) ([]Candle, error) {
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
		if len(row) < 6 { continue }
		ts, e1 := strconv.ParseInt(row[0],10,64)
		vals := make([]float64,5)
		ok := e1 == nil
		for i:=0; i<5 && ok; i++ { vals[i], parseErr = strconv.ParseFloat(row[i+1],64); if parseErr != nil { ok=false } }
		if !ok { continue }
		rows = append(rows,Candle{Timestamp:ts,Open:vals[0],High:vals[1],Low:vals[2],Close:vals[3],Volume:vals[4]})
	}
	return normalize(rows, c.cfg.Now(), limit), nil
}

func (c *Collector) fetchBybit(ctx context.Context, symbol string, limit int) ([]Candle, error) {
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
		if len(row) < 6 { continue }
		ts,e1:=strconv.ParseInt(row[0],10,64)
		vals:=make([]float64,5); var parseErr error; ok:=e1==nil
		for i:=0;i<5 && ok;i++ { vals[i],err=strconv.ParseFloat(row[i+1],64); if err!=nil {ok=false} }
		if !ok {continue}
		rows=append(rows,Candle{Timestamp:ts,Open:vals[0],High:vals[1],Low:vals[2],Close:vals[3],Volume:vals[4]})
	}
	return normalize(rows,c.cfg.Now(),limit),nil
}

func normalize(rows []Candle, now time.Time, limit int) []Candle {
	closedBefore := now.UTC().UnixMilli() / 900000 * 900000
	unique:=map[int64]Candle{}
	for _, row:=range rows {
		if row.Timestamp < 0 || row.Timestamp+900000 > closedBefore {continue}
		if row.Open<=0 || row.High<=0 || row.Low<=0 || row.Close<=0 || row.Volume<0 {continue}
		if row.High < max(row.Open,row.Close,row.Low) || row.Low > min(row.Open,row.Close,row.High) {continue}
		unique[row.Timestamp]=row
	}
	out:=make([]Candle,0,len(unique))
	for _,row:=range unique {out=append(out,row)}
	sort.Slice(out,func(i,j int)bool{return out[i].Timestamp<out[j].Timestamp})
	if len(out)>limit {out=out[len(out)-limit:]}
	return out
}
