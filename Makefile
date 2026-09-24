# Reassemble every hook from src/ into bin/ (needs GNU binutils for m68k: m68k-linux-gnu-as/ld/objcopy/nm).
# The results are committed, so building a firmware image does NOT need this toolchain (see tools/build.py).
AS      = m68k-linux-gnu-as -mcpu=5475
LD      = m68k-linux-gnu-ld
OBJCOPY = m68k-linux-gnu-objcopy
NM      = m68k-linux-gnu-nm

all: bin/tuner.bin bin/tuner_syms.inc bin/scope.bin bin/scope.sym bin/cable.bin bin/cc.bin bin/lock.bin bin/songoff.bin \
     bin/spectrum.bin bin/spec_syms.inc bin/scope_spectrum.bin bin/scope_spectrum.sym

bin/tuner.elf: src/tuner.s
	$(AS) -o bin/tuner.o $<
	$(LD) -Ttext=0x400ac8f0 -e 0x400ac8f0 -o $@ bin/tuner.o
bin/tuner.bin: bin/tuner.elf
	$(OBJCOPY) -O binary $< $@
bin/tuner_syms.inc: bin/tuner.elf
	$(NM) $< | awk '$$3=="TTAP"||$$3=="TUNE"||$$3=="TDRAW"{printf "    .set %s, 0x%s\n",$$3,$$1}' > $@
bin/scope.o: src/scope.s bin/tuner_syms.inc
	$(AS) -I bin -o $@ $<
bin/scope.bin: bin/scope.o
	$(OBJCOPY) -O binary $< $@
bin/scope.sym: bin/scope.o
	$(NM) $< | grep " t " > $@
# page "spectrum"
bin/spec_tables.inc bin/spec_sin.bin: tests/spec_model.py tools/gen_spec_tables.py
	python3 tools/gen_spec_tables.py
bin/spectrum.elf: src/spectrum.s bin/spec_tables.inc
	$(AS) -I bin -o bin/spectrum.o $<
	$(LD) -Ttext=0x400aaa86 -e 0x400aaa86 -o $@ bin/spectrum.o
bin/spectrum.bin: bin/spectrum.elf
	$(OBJCOPY) -O binary $< $@
bin/spec_syms.inc: bin/spectrum.elf
	$(NM) $< | awk '$$3=="SCAP"||$$3=="SPEC"{printf "    .set %s, 0x%s\n",$$3,$$1}' > $@
bin/scope_spectrum.o: src/scope.s bin/tuner_syms.inc bin/spec_syms.inc
	$(AS) -I bin --defsym SPECTRUM=1 -o $@ $<
bin/scope_spectrum.bin: bin/scope_spectrum.o
	$(OBJCOPY) -O binary $< $@
bin/scope_spectrum.sym: bin/scope_spectrum.o
	$(NM) $< | grep " t " > $@

bin/%.bin: src/%.s
	$(AS) -o bin/$*.o $<
	$(OBJCOPY) -O binary bin/$*.o $@

clean:
	rm -f bin/*.o

.PHONY: all clean
