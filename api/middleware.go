package main

import "github.com/gofiber/fiber/v2"

// authMiddleware is a DELIBERATE PASS-THROUGH STUB.
//
// Court/warrant authorization is out of scope for this build. This is the
// single place where warrant checks will later be enforced: validate the
// caller's authorization, resolve the warrant covering the requested number,
// and stash its id in the request context (e.g. c.Locals("warrant_id", ...))
// so handlers / queries can filter on the cdr.warrant_id column.
//
// For now it simply forwards every request unchanged.
func authMiddleware(c *fiber.Ctx) error {
	// TODO(auth): verify caller identity + active warrant for c.Params("number").
	// c.Locals("warrant_id", warrantID)
	return c.Next()
}
