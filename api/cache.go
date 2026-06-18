package main

import (
	"context"
	"time"

	"github.com/redis/go-redis/v9"
)

// Cache is a thin Redis JSON result cache with a short TTL. It is best-effort:
// if Redis is unavailable, Get returns a miss and Set is a no-op, so the API
// keeps serving (just uncached).
type Cache struct {
	rdb *redis.Client
	ttl time.Duration
}

func newCache(addr string, ttl time.Duration) *Cache {
	rdb := redis.NewClient(&redis.Options{Addr: addr})
	return &Cache{rdb: rdb, ttl: ttl}
}

// Get returns cached JSON bytes for key, or (nil, false) on miss/error.
func (c *Cache) Get(ctx context.Context, key string) ([]byte, bool) {
	if c == nil || c.rdb == nil {
		return nil, false
	}
	b, err := c.rdb.Get(ctx, key).Bytes()
	if err != nil {
		return nil, false
	}
	return b, true
}

// Set stores JSON bytes under key with the configured TTL (best-effort).
func (c *Cache) Set(ctx context.Context, key string, b []byte) {
	if c == nil || c.rdb == nil {
		return
	}
	_ = c.rdb.Set(ctx, key, b, c.ttl).Err()
}
