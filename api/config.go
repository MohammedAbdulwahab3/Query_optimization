package main

import (
	"os"
	"strconv"
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
	}
}
