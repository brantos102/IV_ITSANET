-- Crea la base y el usuario de la aplicación en el servidor de la empresa.
--
--   mysql -u root -p < mysql/01-crear-base.sql
--
-- Cambia la contraseña ANTES de ejecutarlo. Las tablas no se crean aquí: las
-- crea la aplicación al arrancar, a partir del modelo, para que no haya dos
-- definiciones del esquema que puedan separarse.

-- utf8mb4, no «utf8».
--
-- El «utf8» de MySQL son tres bytes por carácter: no es UTF-8 completo. Con él,
-- una descripción con un carácter de cuatro bytes se guarda rota o revienta la
-- inserción. utf8mb4 sí es UTF-8 de verdad.
CREATE DATABASE IF NOT EXISTS iv_itsanet
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

-- El usuario solo entra desde la propia máquina. Si la aplicación corre en otro
-- servidor, cambia 'localhost' por su IP; no pongas '%' salvo que haga falta.
CREATE USER IF NOT EXISTS 'itsanet'@'localhost' IDENTIFIED BY 'CAMBIA-ESTA-CLAVE';

-- Lo justo para operar. Sin DROP ni GRANT: la aplicación no necesita borrar
-- tablas, y si algún día lo intenta por un error, que no pueda.
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER, REFERENCES
  ON iv_itsanet.* TO 'itsanet'@'localhost';

FLUSH PRIVILEGES;

-- Comprobación: tiene que decir utf8mb4 y utf8mb4_unicode_ci.
SELECT SCHEMA_NAME, DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME
  FROM information_schema.SCHEMATA
 WHERE SCHEMA_NAME = 'iv_itsanet';
