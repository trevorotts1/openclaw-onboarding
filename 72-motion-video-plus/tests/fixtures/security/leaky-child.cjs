// MG-029 fixture: a child that tries to leak. It prints the values of
// provider-key environment variables when they are present in its own
// environment, and it prints FAKE secret-shaped strings that are
// hardcoded here (clearly synthetic, not real credentials) so tests
// can prove captured output is redacted even when a program prints
// secret-shaped text it invented itself.
//
// Fake values used below (synthetic test strings, safe to commit):
//   Bearer FAKEBEARERTOKEN0123456789
//   api_key=FAKE-LABELED-KEY-0123456789
//   sk-fakeproviderkey0123456789abcd
// The benign control string is a sha256-shaped hex digest, which must
// survive redaction untouched:
//   e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
"use strict";
for (const name of ["KIE_API_KEY", "FISH_AUDIO_API_KEY", "GEMINI_API_KEY", "MG029_PLANTED_SECRET"]) {
  if (process.env[name]) process.stdout.write(name + "=" + process.env[name] + "\n");
}
process.stdout.write("Authorization: Bearer FAKEBEARERTOKEN0123456789\n");
process.stdout.write("api_key=FAKE-LABELED-KEY-0123456789\n");
process.stdout.write("provider key: sk-fakeproviderkey0123456789abcd\n");
process.stdout.write("benign digest e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\n");
