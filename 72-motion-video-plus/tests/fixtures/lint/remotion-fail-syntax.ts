// Invalid module (MG-030 lint fixture): the source does not parse.
// The lint layer reports this as parser_error and runs no rule checks
// it cannot ground in an AST.
export function broken( {
  return 1;
