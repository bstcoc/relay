import { expect, test } from "bun:test";
import { directRequest, Engine, Service } from "../electron/engine";

test("a request line gets its answer line", async () => {
  const service = new Service({ program: "cat", args: [] });
  expect(await service.call('{"id":1}\n')).toBe('{"id":1}');
  expect(await service.call('{"id":2}')).toBe('{"id":2}');
  service.stop();
});

test("a stopped engine is an error", async () => {
  const service = new Service({ program: "true", args: [] });
  await expect(service.call("{}")).rejects.toThrow("the engine stopped");
});

test("an engine that cannot start says so", async () => {
  const service = new Service({ program: "relay-no-such-program", args: [] });
  await expect(service.call("{}")).rejects.toThrow("cannot start the engine");
});

test("only methods without a connection go through the raw engine command", () => {
  const [method, request] = directRequest('{"id":1,"method":"ping"}');
  expect(method).toBe("ping");
  expect(JSON.stringify(request)).toBe('{"id":1,"method":"ping"}');
  for (const blocked of ["connect", "schema", "migrate", "plan", "propose", "suggest"]) {
    expect(() => directRequest(`{"id":1,"method":"${blocked}"}`)).toThrow();
  }
  expect(() => directRequest('{"id":1}')).toThrow();
  expect(() => directRequest('{"id":1,"method":["ping"]}')).toThrow();
  expect(() => directRequest("not json")).toThrow();
});

test("a second request cannot be smuggled after an allowed one", () => {
  expect(() => directRequest('{"id":1,"method":"ping"}\n{"id":2,"method":"migrate"}')).toThrow();
  const [, request] = directRequest('{"id":1,"method":"ping","params":{"note":"a\\nb"}}');
  expect(JSON.stringify(request)).not.toContain("\n");
});

test("a short call is answered while a migration runs", async () => {
  const engine = new Engine(() => ({ program: "cat", args: [] }));
  engine.long.service = new Service({ program: "sh", args: ["-c", "sleep 3"] });
  let finished = false;
  const migration = engine.ask("migrate", {}).finally(() => {
    finished = true;
  });
  await Bun.sleep(200);
  expect(await engine.ask("ping", { id: 1 })).toBe('{"id":1}');
  expect(finished).toBe(false);
  await expect(migration).rejects.toThrow();
  expect(engine.long.service).toBeNull();
  engine.stop();
});

test("a long call frees its engine once answered", async () => {
  const engine = new Engine(() => ({ program: "cat", args: [] }));
  expect(await engine.ask("migrate", { id: 1 })).toBe('{"id":1}');
  expect(engine.long.service).toBeNull();
});

test("calls on the same engine wait for each other", async () => {
  const engine = new Engine(() => ({ program: "cat", args: [] }));
  const answers = await Promise.all([1, 2, 3].map((id) => engine.ask("ping", { id })));
  expect(answers).toEqual(['{"id":1}', '{"id":2}', '{"id":3}']);
  engine.stop();
});
