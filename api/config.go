package main

import (
	"os"
	"strconv"
	"strings"
	"time"
)

// Config holds all runtime configuration, sourced from environment variables
// with sensible defaults for docker-compose.
type Config struct {
	Port string

	CHHost     string
	CHPort     int // native protocol port (9000)
	CHUser     string
	CHPassword string
	CHDatabase string

	MemgraphURI      string
	MemgraphUser     string
	MemgraphPassword string

	RedisAddr string
	CacheTTL  time.Duration

	AuthEnabled bool
	JWTSecret   string
	TokenTTL    time.Duration
	Analysts    map[string]string // username -> password (demo credentials)
}

func env(key, def string) string {
	if v, ok := os.LookupEnv(key); ok && v != "" {
		return v
	}
	return def
}

func envInt(key string, def int) int {
	if v, ok := os.LookupEnv(key); ok && v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

func loadConfig() Config {
	ttlSec := envInt("CACHE_TTL_SECONDS", 30)
	return Config{
		Port: env("PORT", "8080"),

		CHHost:     env("CLICKHOUSE_HOST", "clickhouse"),
		CHPort:     envInt("CLICKHOUSE_PORT", 9000),
		CHUser:     env("CLICKHOUSE_USER", "default"),
		CHPassword: env("CLICKHOUSE_PASSWORD", ""),
		CHDatabase: env("CLICKHOUSE_DATABASE", "telecom"),

		MemgraphURI:      env("MEMGRAPH_URI", "bolt://memgraph:7687"),
		MemgraphUser:     env("MEMGRAPH_USER", ""),
		MemgraphPassword: env("MEMGRAPH_PASSWORD", ""),

		RedisAddr: env("REDIS_ADDR", "redis:6379"),
		CacheTTL:  time.Duration(ttlSec) * time.Second,

		AuthEnabled: env("AUTH_ENABLED", "true") != "false",
		JWTSecret:   env("JWT_SECRET", "insa-cdr-demo-secret-change-me"),
		TokenTTL:    time.Duration(envInt("TOKEN_TTL_HOURS", 8)) * time.Hour,
		Analysts:    parseAnalysts(env("ANALYSTS", "agent.alem:insa-demo,supervisor.bekele:insa-demo")),
	}
}

// parseAnalysts reads "user:pass,user:pass" into a map. Demo-only credential
// store; a real deployment would use an identity provider.
func parseAnalysts(s string) map[string]string {
	m := map[string]string{}
	for _, pair := range splitNonEmpty(s, ",") {
		if i := indexByte(pair, ':'); i > 0 {
			m[pair[:i]] = pair[i+1:]
		}
	}
	return m
}

func splitNonEmpty(s, sep string) []string {
	out := []string{}
	for _, p := range strings.Split(s, sep) {
		if p = strings.TrimSpace(p); p != "" {
			out = append(out, p)
		}
	}
	return out
}

func indexByte(s string, b byte) int {
	for i := 0; i < len(s); i++ {
		if s[i] == b {
			return i
		}
	}
	return -1
}
