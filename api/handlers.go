package main

import (
	"context"
	"encoding/json"
	"fmt"
	"regexp"
	"time"

	"github.com/gofiber/fiber/v2"
)

type Handlers struct {
	ch    *CHStore
	mg    *MGStore
	cache *Cache
}

var numberRe = regexp.MustCompile(`^\d{6,15}$`)

func validNumber(n string) bool { return numberRe.MatchString(n) }

// cached runs compute() unless a fresh cached JSON value exists for key. The
// result is always sent as application/json.
func (h *Handlers) cached(c *fiber.Ctx, key string, compute func() (any, error)) error {
	ctx := c.UserContext()
	if b, ok := h.cache.Get(ctx, key); ok {
		c.Set("X-Cache", "HIT")
		c.Type("json")
		return c.Send(b)
	}
	data, err := compute()
	if err != nil {
		return err
	}
	b, err := json.Marshal(data)
	if err != nil {
		return err
	}
	h.cache.Set(ctx, key, b)
	c.Set("X-Cache", "MISS")
	c.Type("json")
	return c.Send(b)
}

// GET /search/:number
type SearchResponse struct {
	Profile   *Profile   `json:"profile"`
	MapPoints []MapPoint `json:"map_points"`
}

func (h *Handlers) Search(c *fiber.Ctx) error {
	number := c.Params("number")
	if !validNumber(number) {
		return fiber.NewError(fiber.StatusBadRequest, "invalid number format")
	}
	return h.cached(c, "search:"+number, func() (any, error) {
		ctx, cancel := context.WithTimeout(c.UserContext(), 15*time.Second)
		defer cancel()

		profile, err := h.ch.Profile(ctx, number)
		if err != nil {
			return nil, fiber.NewError(fiber.StatusNotFound, "number not found")
		}
		points, err := h.ch.MapPoints(ctx, number, 200)
		if err != nil {
			return nil, err
		}
		return SearchResponse{Profile: profile, MapPoints: points}, nil
	})
}

// GET /graph/:number?depth=1|2
func (h *Handlers) Graph(c *fiber.Ctx) error {
	number := c.Params("number")
	if !validNumber(number) {
		return fiber.NewError(fiber.StatusBadRequest, "invalid number format")
	}
	depth := c.QueryInt("depth", 2)
	if depth < 1 {
		depth = 1
	} else if depth > 2 {
		depth = 2
	}
	key := fmt.Sprintf("graph:%s:%d", number, depth)
	return h.cached(c, key, func() (any, error) {
		ctx, cancel := context.WithTimeout(c.UserContext(), 20*time.Second)
		defer cancel()
		return h.mg.Graph(ctx, number, depth)
	})
}

// GET /timeline/:number?page=&page_size=&from=&to=
type TimelineResponse struct {
	Number   string       `json:"number"`
	Page     int          `json:"page"`
	PageSize int          `json:"page_size"`
	Total    uint64       `json:"total"`
	From     string       `json:"from"`
	To       string       `json:"to"`
	Records  []CallRecord `json:"records"`
}

func (h *Handlers) Timeline(c *fiber.Ctx) error {
	number := c.Params("number")
	if !validNumber(number) {
		return fiber.NewError(fiber.StatusBadRequest, "invalid number format")
	}

	page := c.QueryInt("page", 1)
	if page < 1 {
		page = 1
	}
	pageSize := c.QueryInt("page_size", 50)
	if pageSize < 1 {
		pageSize = 50
	} else if pageSize > 500 {
		pageSize = 500
	}

	// Date-range filter (inclusive from, exclusive to). Defaults: last 10 years.
	from := parseDate(c.Query("from"), time.Now().AddDate(-10, 0, 0))
	to := parseDate(c.Query("to"), time.Now().AddDate(0, 0, 1))

	key := fmt.Sprintf("timeline:%s:%d:%d:%d:%d", number, page, pageSize, from.Unix(), to.Unix())
	return h.cached(c, key, func() (any, error) {
		ctx, cancel := context.WithTimeout(c.UserContext(), 15*time.Second)
		defer cancel()

		offset := (page - 1) * pageSize
		records, total, err := h.ch.Timeline(ctx, number, from, to, pageSize, offset)
		if err != nil {
			return nil, err
		}
		return TimelineResponse{
			Number: number, Page: page, PageSize: pageSize, Total: total,
			From: from.Format("2006-01-02"), To: to.Format("2006-01-02"),
			Records: records,
		}, nil
	})
}

// GET /link/:a/:b
func (h *Handlers) Link(c *fiber.Ctx) error {
	a := c.Params("a")
	b := c.Params("b")
	if !validNumber(a) || !validNumber(b) {
		return fiber.NewError(fiber.StatusBadRequest, "invalid number format")
	}
	key := fmt.Sprintf("link:%s:%s", a, b)
	return h.cached(c, key, func() (any, error) {
		ctx, cancel := context.WithTimeout(c.UserContext(), 20*time.Second)
		defer cancel()
		return h.mg.Link(ctx, a, b)
	})
}

// GET /colocation/:number?window=<minutes>
type CoLocationResponse struct {
	Number    string           `json:"number"`
	WindowMin int              `json:"window_minutes"`
	CoLocated []CoLocatedEvent `json:"co_located"`
}

func (h *Handlers) CoLocation(c *fiber.Ctx) error {
	number := c.Params("number")
	if !validNumber(number) {
		return fiber.NewError(fiber.StatusBadRequest, "invalid number format")
	}
	windowMin := c.QueryInt("window", 10)
	if windowMin < 1 {
		windowMin = 1
	} else if windowMin > 120 {
		windowMin = 120
	}
	key := fmt.Sprintf("colo:%s:%d", number, windowMin)
	return h.cached(c, key, func() (any, error) {
		ctx, cancel := context.WithTimeout(c.UserContext(), 20*time.Second)
		defer cancel()
		events, err := h.ch.CoLocationInTime(ctx, number, windowMin*60, 50)
		if err != nil {
			return nil, err
		}
		return CoLocationResponse{Number: number, WindowMin: windowMin, CoLocated: events}, nil
	})
}

// GET /flags/:number
func (h *Handlers) Flags(c *fiber.Ctx) error {
	number := c.Params("number")
	if !validNumber(number) {
		return fiber.NewError(fiber.StatusBadRequest, "invalid number format")
	}
	return h.cached(c, "flags:"+number, func() (any, error) {
		ctx, cancel := context.WithTimeout(c.UserContext(), 15*time.Second)
		defer cancel()
		return h.ch.Flags(ctx, number)
	})
}

// GET /alerts
func (h *Handlers) Alerts(c *fiber.Ctx) error {
	return h.cached(c, "alerts", func() (any, error) {
		ctx, cancel := context.WithTimeout(c.UserContext(), 30*time.Second)
		defer cancel()
		return h.ch.Alerts(ctx, 50)
	})
}

func parseDate(s string, def time.Time) time.Time {
	if s == "" {
		return def
	}
	if t, err := time.Parse("2006-01-02", s); err == nil {
		return t
	}
	return def
}
