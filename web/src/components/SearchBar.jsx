import React, { useState } from "react";

export default function SearchBar({ onSearch, initial }) {
  const [value, setValue] = useState(initial || "");

  function submit(e) {
    e.preventDefault();
    const n = value.trim();
    if (n) onSearch(n);
  }

  return (
    <form className="searchbar" onSubmit={submit}>
      <input
        type="text"
        inputMode="numeric"
        placeholder="Enter subscriber number e.g. 251911000001"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <button type="submit">Search</button>
    </form>
  );
}
