CREATE TABLE creators (
 id TEXT PRIMARY KEY,
 name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 128),
 kind TEXT NOT NULL CHECK(kind IN ('person','team','company')),
 brand TEXT NOT NULL CHECK(length(brand)<=128),
 homepage_url TEXT NOT NULL CHECK(length(homepage_url)<=512),
 profile_url TEXT NOT NULL CHECK(length(profile_url)<=512),
 contact TEXT NOT NULL CHECK(length(contact)<=256),
 country TEXT NOT NULL CHECK(length(country)<=64),
 description TEXT NOT NULL CHECK(length(description)<=512),
 enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
 revision INTEGER NOT NULL CHECK(revision>0)
);
CREATE INDEX creators_enabled_id ON creators(enabled,id);
