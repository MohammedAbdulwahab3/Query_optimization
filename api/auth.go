package main

import (
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/golang-jwt/jwt/v5"
)

// Auth issues and verifies analyst JWTs against a demo credential store.
type Auth struct {
	secret   []byte
	ttl      time.Duration
	analysts map[string]string
	enabled  bool
}

func newAuth(cfg Config) *Auth {
	return &Auth{
		secret:   []byte(cfg.JWTSecret),
		ttl:      cfg.TokenTTL,
		analysts: cfg.Analysts,
		enabled:  cfg.AuthEnabled,
	}
}

func (a *Auth) issue(analyst string) (string, error) {
	claims := jwt.MapClaims{
		"sub": analyst,
		"exp": time.Now().Add(a.ttl).Unix(),
		"iat": time.Now().Unix(),
	}
	return jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString(a.secret)
}

// analystFromToken returns the analyst subject for a valid bearer token.
func (a *Auth) analystFromToken(bearer string) (string, bool) {
	if len(bearer) > 7 && bearer[:7] == "Bearer " {
		bearer = bearer[7:]
	}
	tok, err := jwt.Parse(bearer, func(t *jwt.Token) (any, error) {
		if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, jwt.ErrSignatureInvalid
		}
		return a.secret, nil
	})
	if err != nil || !tok.Valid {
		return "", false
	}
	claims, ok := tok.Claims.(jwt.MapClaims)
	if !ok {
		return "", false
	}
	sub, _ := claims["sub"].(string)
	return sub, sub != ""
}

// POST /auth/login {username, password} -> {token, analyst}
func (a *Auth) Login(c *fiber.Ctx) error {
	var body struct {
		Username string `json:"username"`
		Password string `json:"password"`
	}
	if err := c.BodyParser(&body); err != nil {
		return fiber.NewError(fiber.StatusBadRequest, "invalid body")
	}
	pass, ok := a.analysts[body.Username]
	if !ok || pass != body.Password {
		return fiber.NewError(fiber.StatusUnauthorized, "invalid credentials")
	}
	token, err := a.issue(body.Username)
	if err != nil {
		return err
	}
	return c.JSON(fiber.Map{"token": token, "analyst": body.Username})
}
