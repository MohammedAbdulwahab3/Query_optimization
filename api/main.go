package main

import (
	"context"
	"log"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/cors"
	"github.com/gofiber/fiber/v2/middleware/logger"
	"github.com/gofiber/fiber/v2/middleware/recover"
)

func main() {
	cfg := loadConfig()

	// --- connect to stores (with a short retry window for compose startup) ---
	ch := mustCH(cfg)
	mg := mustMG(cfg)
	defer mg.close(context.Background())
	cache := newCache(cfg.RedisAddr, cfg.CacheTTL)

	h := &Handlers{ch: ch, mg: mg, cache: cache}
	app := buildApp(h)

	log.Printf("listening on :%s", cfg.Port)
	log.Fatal(app.Listen(":" + cfg.Port))
}

// buildApp wires middleware and routes. Extracted so tests can exercise the
// HTTP layer without live datastores.
func buildApp(h *Handlers) *fiber.App {
	app := fiber.New(fiber.Config{
		AppName:      "Telecom CDR Analytics API",
		ErrorHandler: errorHandler,
	})
	app.Use(recover.New())
	app.Use(logger.New())
	app.Use(cors.New())

	app.Get("/health", func(c *fiber.Ctx) error {
		return c.JSON(fiber.Map{"status": "ok"})
	})

	// Auth seam: the pass-through stub guards every analytics route. Warrant
	// checks slot in here later without touching handlers.
	api := app.Group("/", authMiddleware)
	api.Get("/search/:number", h.Search)
	api.Get("/graph/:number", h.Graph)
	api.Get("/timeline/:number", h.Timeline)
	return app
}

func mustCH(cfg Config) *CHStore {
	var lastErr error
	for i := 0; i < 30; i++ {
		s, err := newCHStore(cfg)
		if err == nil {
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			err = s.ping(ctx)
			cancel()
			if err == nil {
				log.Println("connected to ClickHouse")
				return s
			}
		}
		lastErr = err
		log.Printf("waiting for ClickHouse (%d/30): %v", i+1, err)
		time.Sleep(2 * time.Second)
	}
	log.Fatalf("ClickHouse unavailable: %v", lastErr)
	return nil
}

func mustMG(cfg Config) *MGStore {
	var lastErr error
	for i := 0; i < 30; i++ {
		s, err := newMGStore(cfg)
		if err == nil {
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			err = s.ping(ctx)
			cancel()
			if err == nil {
				log.Println("connected to Memgraph")
				return s
			}
		}
		lastErr = err
		log.Printf("waiting for Memgraph (%d/30): %v", i+1, err)
		time.Sleep(2 * time.Second)
	}
	log.Fatalf("Memgraph unavailable: %v", lastErr)
	return nil
}

func errorHandler(c *fiber.Ctx, err error) error {
	code := fiber.StatusInternalServerError
	if e, ok := err.(*fiber.Error); ok {
		code = e.Code
	}
	return c.Status(code).JSON(fiber.Map{"error": err.Error()})
}
