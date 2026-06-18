package main

import (
	"strings"

	"github.com/gofiber/fiber/v2"
)

// This file is the auth seam that was stubbed in the first build. It now
// enforces lawful-interception controls:
//   requireAuth  — every analytics route needs a valid analyst JWT.
//   warrantGate  — access to a specific number needs an ACTIVE warrant; every
//                  access (allowed or denied) is written to the audit log.

// requireAuth validates the analyst bearer token and stashes the analyst id.
func (h *Handlers) requireAuth(c *fiber.Ctx) error {
	if !h.auth.enabled {
		c.Locals("analyst", "anonymous")
		return c.Next()
	}
	analyst, ok := h.auth.analystFromToken(c.Get("Authorization"))
	if !ok {
		return fiber.NewError(fiber.StatusUnauthorized, "authentication required")
	}
	c.Locals("analyst", analyst)
	return c.Next()
}

// warrantGate enforces that every targeted number is covered by an active
// warrant, auditing the outcome. Targets are the :number / :a / :b route params.
func (h *Handlers) warrantGate(c *fiber.Ctx) error {
	analyst, _ := c.Locals("analyst").(string)
	if analyst == "" {
		analyst = "anonymous"
	}
	action := routeAction(c.Path())
	ctx := c.UserContext()

	targets := []string{}
	for _, key := range []string{"number", "a", "b"} {
		if v := c.Params(key); v != "" {
			targets = append(targets, v)
		}
	}

	if !h.auth.enabled {
		return c.Next() // warrants not enforced when auth disabled
	}

	warrantID := ""
	for _, t := range targets {
		id, _ := h.ch.ActiveWarrant(ctx, t)
		if id == "" {
			h.ch.WriteAudit(ctx, analyst, action, t, "", "denied", c.IP())
			return fiber.NewError(fiber.StatusForbidden,
				"no active warrant for "+t)
		}
		if warrantID == "" {
			warrantID = id
		}
	}
	for _, t := range targets {
		h.ch.WriteAudit(ctx, analyst, action, t, warrantID, "allowed", c.IP())
	}
	c.Locals("warrant_id", warrantID)
	return c.Next()
}

// auditOnly records access to dataset-wide endpoints (no single target).
func (h *Handlers) auditOnly(action string) fiber.Handler {
	return func(c *fiber.Ctx) error {
		analyst, _ := c.Locals("analyst").(string)
		if h.auth.enabled {
			h.ch.WriteAudit(c.UserContext(), analyst, action, "*", "", "allowed", c.IP())
		}
		return c.Next()
	}
}

func routeAction(path string) string {
	parts := strings.Split(strings.Trim(path, "/"), "/")
	if len(parts) > 0 && parts[0] != "" {
		return parts[0]
	}
	return "access"
}
