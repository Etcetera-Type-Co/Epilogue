#!/bin/sh

set -e


cd sources

echo "Generating Static fonts"
mkdir -p ../fonts/static/ttf
fontmake -g Epilogue.glyphs -i -o ttf --output-dir ../fonts/static/ttf/

mkdir -p ../fonts/static/otf
fontmake -g Epilogue.glyphs -i -o otf --output-dir ../fonts/static/otf/




cd ..

# ============================================================================
# Autohinting ================================================================


echo "Post processing TTFs"
ttfs=$(ls fonts/static/ttf/*.ttf)
for ttf in $ttfs
do
	gftools fix-dsig -f $ttf;
	ttfautohint $ttf $ttf.fix
	mv "$ttf.fix" $ttf;
	gftools fix-hinting $ttf
	mv "$ttf.fix" $ttf;
done

echo "Post processing OTFs"
otfs=$(ls fonts/static/otf/*.otf)
for otf in $otfs
do
	gftools fix-dsig -f $otf
done


# ============================================================================
# Build woff2 fonts ==========================================================

# requires https://github.com/bramstein/homebrew-webfonttools

rm -rf fonts/web/woff2

ttfs=$(ls fonts/static/ttf/*.ttf)
for ttf in $ttfs; do
    woff2_compress $ttf
done

mkdir -p fonts/web/woff2
woff2s=$(ls fonts/static/*/*.woff2)
for woff2 in $woff2s; do
    mv $woff2 fonts/web/woff2/$(basename $woff2)
done
# ============================================================================
# Build woff fonts ==========================================================

# requires https://github.com/bramstein/homebrew-webfonttools

rm -rf fonts/web/woff

ttfs=$(ls fonts/static/ttf/*.ttf)
for ttf in $ttfs; do
    sfnt2woff-zopfli $ttf
done

mkdir -p fonts/web/woff
woffs=$(ls fonts/static/*/*.woff)
for woff in $woffs; do
    mv $woff fonts/web/woff/$(basename $woff)
done



cd sources

echo "Generating VFs"
mkdir -p ../fonts/variable
fontmake -g Epilogue.glyphs -o variable --output-path ../fonts/variable/Epilogue[slnt,wght].ttf

rm -rf master_ufo/ instance_ufo/


cd ../fonts/variable

woff2_compress Epilogue[slnt,wght].ttf

cd ..

echo "Post processing"


vfs=$(ls ../fonts/variable/*.ttf)
for vf in $vfs
do
  gftools fix-dsig -f $vf;
  gftools fix-nonhinting $vf $vf.fix;
  mv "$vf.fix" $vf;
	ttx -f -x "MVAR" $vf; # Drop MVAR. Table has issue in DW
	rtrip=$(basename -s .ttf $vf)
	new_file=../fonts/variable/$rtrip.ttx;
	rm $vf;
	ttx $new_file
	rm ../fonts/variable/*.ttx
done
rm ../fonts/variable/*gasp.ttf

echo "Complete!"
