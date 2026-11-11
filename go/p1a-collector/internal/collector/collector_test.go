package collector

import (
	"context"
	"fmt"
	"math"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestCollectUsesOKXAndSortsClosedCandles(t *testing.T) {
	now := time.Date(2026, 11, 11, 12, 7, 0, 0, time.UTC)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.Contains(r.URL.Path, "/api/v5/market/candles") { t.Fatalf("unexpected path %s", r.URL.Path) }
		w.Header().Set("Content-Type", "application/json")
		// 12:00 is still open; 11:45 is closed.
		_, _ = w.Write([]byte(`{"code":"0","data":[["1794398400000","3","4","2","3.5","10","10","10","0"],["1794397500000","2","3","1","2.5","9","9","9","1"]]}`))
	}))
	defer srv.Close()
	c := New(Config{OKXBaseURL:srv.URL, BybitBaseURL:srv.URL, HTTPClient:srv.Client(), Workers:2, Now:func()time.Time{return now}})
	got,err:=c.Collect(context.Background(),Request{Symbols:[]string{"BTCUSDT"},Timeframe:"15m",Limit:100})
	if err!=nil {t.Fatal(err)}
	if len(got.Results)!=1 || got.Results[0].Provider!="okx" || got.Results[0].Status!="OK" {t.Fatalf("unexpected result: %+v",got)}
	if len(got.Results[0].Candles)!=1 {t.Fatalf("expected only one closed candle, got %d",len(got.Results[0].Candles))}
}

func TestFallsBackPerSymbolWithoutMixing(t *testing.T) {
	now:=time.Date(2026,11,11,12,7,0,0,time.UTC)
	var okxCalls,bybitCalls int
	okx:=httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){okxCalls++;w.WriteHeader(451)}));defer okx.Close()
	bybit:=httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){
		bybitCalls++;w.Header().Set("Content-Type","application/json")
		_,_=w.Write([]byte(`{"retCode":0,"result":{"list":[["1794397500000","2","3","1","2.5","9","9","9","1"]]}}`))
	}));defer bybit.Close()
	c:=New(Config{OKXBaseURL:okx.URL,BybitBaseURL:bybit.URL,HTTPClient:bybit.Client(),Workers:1,Now:func()time.Time{return now}})
	got,err:=c.Collect(context.Background(),Request{Symbols:[]string{"ETHUSDT"},Limit:100})
	if err!=nil {t.Fatal(err)}
	if got.Results[0].Provider!="bybit" || got.Results[0].Status!="OK" {t.Fatalf("fallback failed: %+v",got.Results[0])}
	if okxCalls!=1 || bybitCalls!=1 {t.Fatalf("unexpected calls: okx=%d bybit=%d",okxCalls,bybitCalls)}
}

func TestRejectsDuplicateAndNonUSDT(t *testing.T) {
	c:=New(Config{})
	if _,err:=c.Collect(context.Background(),Request{Symbols:[]string{"BTCUSDT","BTCUSDT"}});err==nil {t.Fatal("duplicate symbol accepted")}
	if _,err:=c.Collect(context.Background(),Request{Symbols:[]string{"BTCUSD"}});err==nil {t.Fatal("non-USDT symbol accepted")}
}

func TestNoDataIsExplicitlyUnavailable(t *testing.T) {
	srv:=httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){w.Header().Set("Content-Type","application/json");_,_=w.Write([]byte(`{"code":"0","data":[]}`))}))
	defer srv.Close()
	c:=New(Config{OKXBaseURL:srv.URL,BybitBaseURL:srv.URL,HTTPClient:srv.Client()})
	got,err:=c.Collect(context.Background(),Request{Symbols:[]string{"SOLUSDT"}})
	if err!=nil {t.Fatal(err)}
	if got.Results[0].Status!="UNAVAILABLE" || len(got.Results[0].Candles)!=0 {t.Fatalf("bad unavailable state: %+v",got.Results[0])}
}

func TestNormalizeRejectsDuplicateTimestamp(t *testing.T) {
	now := time.Date(2026, 11, 11, 12, 7, 0, 0, time.UTC)
	rows := []Candle{
		{Timestamp:1794397500000, Open:2, High:3, Low:1, Close:2.5, Volume:9},
		{Timestamp:1794397500000, Open:2, High:3, Low:1, Close:2.5, Volume:9},
	}
	if _, err := normalize(rows, now, 100); err == nil || !strings.Contains(err.Error(), "DUPLICATE_TIMESTAMP") {
		t.Fatalf("expected duplicate timestamp rejection, got %v", err)
	}
}

func TestNormalizeRejectsDataGap(t *testing.T) {
	now := time.Date(2026, 11, 11, 12, 37, 0, 0, time.UTC)
	rows := []Candle{
		{Timestamp:1794396600000, Open:2, High:3, Low:1, Close:2.5, Volume:9},
		{Timestamp:1794398400000, Open:2, High:3, Low:1, Close:2.5, Volume:9},
	}
	if _, err := normalize(rows, now, 100); err == nil || !strings.Contains(err.Error(), "DATA_GAP_OR_INTERVAL_ERROR") {
		t.Fatalf("expected gap rejection, got %v", err)
	}
}

func TestNormalizeRejectsNonFiniteValues(t *testing.T) {
	now := time.Date(2026, 11, 11, 12, 7, 0, 0, time.UTC)
	rows := []Candle{{Timestamp:1794397500000, Open:2, High:3, Low:1, Close:2.5, Volume:math.NaN()}}
	if _, err := normalize(rows, now, 100); err == nil || !strings.Contains(err.Error(), "NON_FINITE_CANDLE_VALUE") {
		t.Fatalf("expected non-finite rejection, got %v", err)
	}
}

func TestCollectorBoundsConcurrencyAcrossFortySymbols(t *testing.T) {
	var active int32
	var maxActive int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		current := atomic.AddInt32(&active, 1)
		for {
			old := atomic.LoadInt32(&maxActive)
			if current <= old || atomic.CompareAndSwapInt32(&maxActive, old, current) { break }
		}
		time.Sleep(10 * time.Millisecond)
		atomic.AddInt32(&active, -1)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"code":"0","data":[["1794397500000","2","3","1","2.5","9","9","9","1"]]}`))
	}))
	defer srv.Close()
	symbols := make([]string, 40)
	for i := range symbols { symbols[i] = fmt.Sprintf("COIN%dUSDT", i) }
	now := time.Date(2026, 11, 11, 12, 7, 0, 0, time.UTC)
	c := New(Config{OKXBaseURL:srv.URL, BybitBaseURL:srv.URL, HTTPClient:srv.Client(), Workers:2, Now:func()time.Time{return now}})
	got, err := c.Collect(context.Background(), Request{Symbols:symbols, Limit:10})
	if err != nil { t.Fatal(err) }
	if len(got.Results) != 40 { t.Fatalf("expected 40 results, got %d", len(got.Results)) }
	if atomic.LoadInt32(&maxActive) < 2 || atomic.LoadInt32(&maxActive) > 2 {
		t.Fatalf("expected bounded concurrency of 2, observed %d", atomic.LoadInt32(&maxActive))
	}
}
