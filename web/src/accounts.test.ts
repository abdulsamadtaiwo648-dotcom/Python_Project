import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { canTransfer, hasOneAccount, isNairaAmount, openingBalanceOrZero, pickableAccounts } from "./accounts";

describe("opening balance text", () => {
  test("plain, comma-separated and negative amounts are accepted", () => {
    assert.equal(isNairaAmount("5000"), true);
    assert.equal(isNairaAmount("5,000.50"), true);
    assert.equal(isNairaAmount("-500"), true);
  });

  test("text that is not money is refused", () => {
    assert.equal(isNairaAmount("abc"), false);
    assert.equal(isNairaAmount("12.345"), false);
    assert.equal(isNairaAmount("1e3"), false);
    assert.equal(isNairaAmount("-"), false);
    assert.equal(isNairaAmount(""), false);
  });

  test("a blank opening balance is zero", () => {
    assert.equal(openingBalanceOrZero("   "), "0");
    assert.equal(openingBalanceOrZero(" 250 "), "250");
  });
});

describe("account choices", () => {
  const accounts = [
    { id: 1, archived: false },
    { id: 2, archived: true },
    { id: 3, archived: false },
  ];

  test("an archived account is offered only when an entry already uses it", () => {
    assert.deepEqual(pickableAccounts(accounts, null).map((a) => a.id), [1, 3]);
    assert.deepEqual(pickableAccounts(accounts, 2).map((a) => a.id), [1, 2, 3]);
  });

  test("selectors are hidden with one active account", () => {
    assert.equal(hasOneAccount([{ archived: false }]), true);
    assert.equal(hasOneAccount([{ archived: false }, { archived: true }]), true);
    assert.equal(hasOneAccount(accounts), false);
  });

  test("a transfer needs two active accounts", () => {
    assert.equal(canTransfer([{ archived: false }]), false);
    assert.equal(canTransfer([{ archived: false }, { archived: true }]), false);
    assert.equal(canTransfer([{ archived: false }, { archived: false }]), true);
  });
});
